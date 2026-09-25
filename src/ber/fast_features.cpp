// Optional native implementation of features.py, using MIT-licensed RapidFuzz.
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <rapidfuzz/fuzz.hpp>
#include <rapidfuzz/distance/JaroWinkler.hpp>
#include <algorithm>
#include <unordered_map>
#include <set>
#include <string>
#include <vector>

using Text = std::u32string;
struct Parts {
    Text text, compact;
    std::set<Text> words, numbers;
    std::vector<Text> digits;
    explicit Parts(Text value): text(std::move(value)) {
        Text word, number;
        for (auto ch: text) {
            if (ch != U' ') compact += ch;
            if (Py_UNICODE_ISSPACE(ch)) {
                if (!word.empty()) { words.insert(word); word.clear(); }
            } else word += ch;
            if (Py_UNICODE_ISDECIMAL(ch)) number += ch;
            else if (!number.empty()) { digits.push_back(number); numbers.insert(number); number.clear(); }
        }
        if (!word.empty()) words.insert(word);
        if (!number.empty()) { digits.push_back(number); numbers.insert(number); }
    }
};

static size_t intersection(const std::set<Text>& a, const std::set<Text>& b) {
    auto i=a.begin(), j=b.begin(); size_t n=0;
    while (i!=a.end() && j!=b.end()) {
        if (*i<*j) ++i; else if (*j<*i) ++j; else {++n; ++i; ++j;}
    }
    return n;
}
static void overlap(float*& out, const std::set<Text>& a, const std::set<Text>& b) {
    double n=intersection(a,b);
    *out++=n/std::max(1.0, double(a.size()+b.size())-n);
    *out++=n/std::max(size_t(1), std::min(a.size(),b.size()));
    *out++=n/std::max(size_t(1), a.size());
    *out++=n/std::max(size_t(1), b.size());
}
static void field(float*& out, const Parts& l, const Parts& r) {
    *out++=rapidfuzz::fuzz::ratio(l.text,r.text)/100;
    *out++=rapidfuzz::fuzz::token_sort_ratio(l.text,r.text)/100;
    *out++=rapidfuzz::fuzz::token_set_ratio(l.text,r.text)/100;
    *out++=rapidfuzz::fuzz::ratio(l.compact,r.compact)/100;
    *out++=rapidfuzz::jaro_winkler_similarity(l.text,r.text);
    *out++=!l.text.empty() && l.text==r.text;
    *out++=l.text.size(); *out++=r.text.size();
    *out++=double(std::min(l.text.size(),r.text.size()))/std::max(size_t(1),std::max(l.text.size(),r.text.size()));
    overlap(out,l.words,r.words); overlap(out,l.numbers,r.numbers);
    bool both=!l.digits.empty() && !r.digits.empty();
    *out++=both && l.digits.front()==r.digits.front();
    *out++=both && l.digits.back()==r.digits.back();
    *out++=both && intersection(l.numbers,r.numbers)==0;
    *out++=l.text.empty(); *out++=r.text.empty();
}

static PyObject* batch(PyObject*, PyObject* records) {
    PyObject* seq=PySequence_Fast(records,"records must be a sequence");
    if (!seq) return nullptr;
    Py_ssize_t n=PySequence_Fast_GET_SIZE(seq);
    PyObject* result=PyBytes_FromStringAndSize(nullptr,n*47*sizeof(float));
    if (!result) { Py_DECREF(seq); return nullptr; }
    float* out=reinterpret_cast<float*>(PyBytes_AS_STRING(result));
    try {
        std::unordered_map<Text,Parts> cache;
        cache.reserve(std::min(Py_ssize_t(100000),n*2));
        for (Py_ssize_t i=0;i<n;++i) {
            PyObject* row=PySequence_Fast(PySequence_Fast_GET_ITEM(seq,i),"row must be a sequence");
            if (!row) {Py_DECREF(seq);Py_DECREF(result);return nullptr;}
            if (PySequence_Fast_GET_SIZE(row)!=7) {Py_DECREF(row);Py_DECREF(seq);Py_DECREF(result);PyErr_SetString(PyExc_ValueError,"expected seven fields");return nullptr;}
            const Parts* parsed[4];
            bool valid=true;
            for (int k=0;k<4;++k) {
                PyObject* value=PySequence_Fast_GET_ITEM(row,k);
                if (!PyUnicode_Check(value)) {valid=false; PyErr_SetString(PyExc_TypeError,"text must be str");break;}
                Py_UCS4* raw=PyUnicode_AsUCS4Copy(value);
                if (!raw) {valid=false;break;}
                Text text(reinterpret_cast<char32_t*>(raw),PyUnicode_GET_LENGTH(value));
                PyMem_Free(raw);
                auto found=cache.find(text);
                if (found==cache.end()) found=cache.emplace(text,Parts(text)).first;
                parsed[k]=&found->second;
            }
            if (valid) {
                field(out,*parsed[0],*parsed[2]); field(out,*parsed[1],*parsed[3]);
                for (int k=4;k<7;++k) *out++=PyFloat_AsDouble(PySequence_Fast_GET_ITEM(row,k));
            }
            Py_DECREF(row);
            if (!valid || PyErr_Occurred()) {Py_DECREF(seq);Py_DECREF(result);return nullptr;}
        }
    } catch (const std::exception& e) {Py_DECREF(seq);Py_DECREF(result);PyErr_SetString(PyExc_RuntimeError,e.what());return nullptr;}
    Py_DECREF(seq);
    return result;
}
static PyMethodDef methods[]={{"batch",batch,METH_O,"Return 47 float32 features per row as bytes."},{nullptr,nullptr,0,nullptr}};
static PyModuleDef module={PyModuleDef_HEAD_INIT,"_fast_features",nullptr,-1,methods};
PyMODINIT_FUNC PyInit__fast_features() {return PyModule_Create(&module);}
