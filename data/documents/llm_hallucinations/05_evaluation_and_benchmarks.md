# Evaluation Benchmarks and Detection Metrics for Hallucinations

## 1. Standard Benchmark Datasets
- **TruthfulQA**: Evaluates whether a language model mimics human false beliefs and conspiracy theories across 38 subject categories.
- **HaluEval**: Large-scale benchmark containing 35,000+ generated and human-annotated hallucinations across QA, dialogue, and summarization.
- **FaithDial**: Specialized dataset for measuring conversational hallucination in knowledge-grounded dialogue systems.
- **FActScore**: Fine-grained atomic fact verification framework that decomposes biographical text into atomic claims and evaluates precision against Wikipedia.

## 2. Automated Detection Frameworks
- **NLI-Based Consistency**: Uses Natural Language Inference models (RoBERTa-MNLI) to check if generated sentences are logically entailed by source contexts.
- **SelfCheckGPT**: Zero-resource hallucination detection method that measures consistency across stochastic stochastic stochastic response samples without requiring external knowledge bases.
