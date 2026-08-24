# Root Causes of Hallucinations in Large Language Models

## 1. Pretraining Limitations
The primary objective of autoregressive language models is statistical likelihood minimization:
\[ P(w_t \mid w_1, w_2, \dots, w_{t-1}) \]
Because the model optimizes for sequence plausibility rather than objective truth, plausible-sounding falsehoods receive high probability scores.

## 2. Dataset Quality and Noise
- **Noisy Web Scrapes**: Training corpora contain misinformation, satire, outdated facts, and conflicting viewpoints.
- **Exposure Bias**: Imbalance in knowledge representation causes models to favor statistically dominant but factually inaccurate patterns.
- **Knowledge Cutoff**: Temporal boundaries prevent models from knowing events after training.

## 3. Architectural and Decoding Factors
- **Attention Drift**: Over long context windows, attention dispersal can cause the model to ignore critical factual constraints in the prompt.
- **Sampling Stochasticity**: High temperature and top-p decoding parameters increase linguistic creativity at the expense of factual precision.
- **Superficial Alignment**: RLHF can inadvertently teach models to optimize for helpfulness and persuasiveness over strict accuracy.
