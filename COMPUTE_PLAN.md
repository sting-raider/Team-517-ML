# Compute plan — Amazon ML Challenge 2026

Updated 25 September 2026 using the hardware and credit budget reported by the user. This is a proposed allocation; no AWS resources have been started and no account balance or quota has been inspected.

Implementation update: local RAM is 16 GB. The supplied files contain 24,229,173
records. CPU baselines, country-transfer tests, and disk-backed indexes are running;
CUDA PyTorch is installed in `.venv-gpu`. The user clarified that validation quality
takes priority over saving computation. Candidate/model limits must be justified by
measured score or genuine feasibility constraints, not an assumed preference for
cheap inference. The earlier 30-candidate speed trade-off has been withdrawn from
production selection. No AWS spending has occurred.

The team has enough local GPU memory to attempt the proposed compact encoder-based pipeline. Whether all training and inference finish before the deadline depends on record counts, candidate counts, sequence lengths, system RAM, and sustained laptop throughput. Problem difficulty alone is not a reliable predictor of required compute.

## Local allocation

| Machine | Proposed responsibility | Initial scope |
|---|---|---|
| RTX 3060 6 GB; i7-12700H | Data audit, scorer, sparse retrieval, feature matcher, calibration; small GPU smoke tests | CPU workloads within available system RAM; compact encoder inference or small-batch training |
| RTX 4080 laptop 12 GB; i9-13900HX — first teammate | Cross-encoder training | One base-sized encoder, short record-pair sequences, mixed precision and measured batch size |
| RTX 4080 laptop 12 GB; i9-13900HX — second teammate | Country-transfer validation, then multilingual encoder or learned retriever experiments | US-to-India and India-to-US stress tests now have priority because France is test-only |

These are proposed human/machine responsibilities, not delegated agent tasks. The laptop VRAM capacities do not combine into one 30 GB device. Run independent experiments or inference shards. Synchronizing one training run over ordinary inter-laptop networking would add setup and communication overhead.

Start with an encoder in roughly the 100–150 million parameter class, rather than assuming a multi-billion-parameter generative model is required. A 12 GB GPU is a reasonable target for experimenting with this class at short sequence lengths, but actual fit must be measured. On 6 GB, reduce the physical batch and consider a smaller encoder or gradient checkpointing.

Choose sequence length using actual token lengths; 128 and 256 tokens are candidate configurations, not unconditional limits. Use mixed precision and gradient accumulation where appropriate. Gradient accumulation increases the effective optimization batch, but does not automatically create the same cross-example negative pool as a larger contrastive batch. Use multi-positive batches and a properly designed cache/queue if extra contrastive negatives are needed.

Track examples per second, peak GPU memory, CPU/RAM usage, and sustained performance after warm-up. Keep the laptops powered and configured not to sleep during runs. Freeze the same fold definitions, normalization, and candidate IDs across machines; record checkpoint/config hashes and exchange predictions keyed by IDs for ensembling.

## When AWS earns its cost

Use cloud compute when a measured condition justifies it:

1. The useful model or contrastive batch does not fit in 12 GB after reasonable memory optimization.
2. Projected full-data scoring would miss the deadline.
3. More independent folds or a validated complementary model are worth running concurrently.
4. Sparse indexes or feature tables need more system RAM than the laptops have.

A larger-memory CPU instance may solve the fourth case without requiring a more expensive GPU. A cloud GPU is not automatically faster than a laptop GPU on every small-model workload; compare throughput on the same sample.

| AWS candidate | GPU memory class advertised by AWS | Proposed use |
|---|---|---|
| g6.xlarge / g6.2xlarge | One NVIDIA L4, 24 GB | More headroom for batches and inference; 2xlarge provides more host CPU/RAM |
| g5.xlarge / g5.2xlarge | One NVIDIA A10G, 24 GB | Alternative to benchmark according to regional price and availability |
| g6e.xlarge / g6e.2xlarge | One NVIDIA L40S, 48 GB | Larger-memory training or batched inference if 24 GB is insufficient |

Sources: [AWS G6](https://aws.amazon.com/ec2/instance-types/g6/), [AWS G5](https://aws.amazon.com/ec2/instance-types/g5/), [AWS G6e](https://aws.amazon.com/ec2/instance-types/g6e/). These are advertised memory classes; AWS's technical specifications may express usable memory in GiB. Choose instance size based on host RAM and CPU as well as GPU. This plan does not claim these instances are accessible in the team's account.

## Budget and launch conditions

Treat the reported $650 as a ceiling, not a spending target. An initial proposed allocation is $50 for cloud benchmarking/setup, up to $300 for experiments that earn their cost, $200 reserved for final training/inference, and $100 for storage, reruns, and contingency. Unneeded allocation remains unspent.

Illustrative arithmetic, **not verified regional price quotes**:

| Combined hourly compute rate | 24 hours | 48 hours | 72 hours |
|---:|---:|---:|---:|
| $1/hour | $24 | $48 | $72 |
| $2/hour | $48 | $96 | $144 |
| $4/hour | $96 | $192 | $288 |

For example, two instances each billed at $2/hour for 48 hours cost $192 in compute. Storage, transfer, public IP, software fees, and other services can add to the bill. Exact current pricing was not established for the team's region/account; obtain it from the [AWS Pricing Calculator](https://calculator.aws/) or launch console before selecting a machine.

Before a launch, inspect which account holds each credit, its eligible services/expiry, and the regional EC2 GPU quota. Credits do not guarantee service access or instance capacity, and separate teammates' balances are not automatically a single pool. [AWS credit terms](https://aws.amazon.com/awscredits/), [EC2 quotas](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html).

Use checkpointed jobs with an explicit maximum runtime and a shutdown path. Budget notifications are useful but are not an instantaneous hard spending cap. Persist checkpoints before stopping the machine, and account for retained storage. Consider interruptible capacity only for restartable jobs with time to recover; final deadline-critical scoring should prioritize completion.

## Pretrained models and next step

The supplied Problem Statement restricts the final model to MIT/Apache 2.0 licensing and at most 8 billion parameters. Check each checkpoint's actual license and parameter count; open weights or a permissive library license alone are insufficient. Plan a compact eligible multilingual encoder comparison because France occurs only in test. External business lookup, entity-resolution services, geocoding APIs, and internet-derived data augmentation are prohibited; AWS here means rented compute for our own pipeline.

The Guidelines prohibit simultaneous portal logins across devices per participant. Keep portal sessions separate from distributed training work and do not share one participant's active login across the team's laptops. Neither PDF expressly prohibits training on multiple machines. See RULES_INSIGHTS.md for exact requirements and unresolved document differences.

The next practical step is still the dataset audit. It determines whether the critical resource is GPU memory, GPU hours, host RAM, or simply better candidates. Do not choose a large cloud machine solely from the perceived difficulty of the private test.
