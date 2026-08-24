# Taxonomy of Hallucinations in Large Language Models

## 1. Definition and Core Concepts
In Large Language Models (LLMs), a hallucination refers to generated text that is unfaithful to the provided source context or factually incorrect according to real-world knowledge. Unlike human memory errors, LLM hallucinations stem from probabilistic next-token generation without grounding in truth.

## 2. Primary Classification
Hallucinations are broadly classified into two major categories:

### Factuality Hallucinations
Occur when the generated content contradicts established real-world facts.
- **Factual Inconsistency**: The model asserts false claims about historical dates, scientific facts, or well-known entities.
- **Factual Fabrication**: The model invents nonexistent citations, legal precedents, authors, or biological compounds.

### Faithfulness Hallucinations
Occur in context-grounded tasks (e.g., summarization, question answering, translation) where the output deviates from the reference input.
- **Intrinsic Hallucination**: The generated text directly contradicts facts stated in the source text.
- **Extrinsic Hallucination**: The generated text introduces extraneous details that cannot be verified or substantiated from the source text.

## 3. Behavioral Manifestations
- **Sycophancy**: The model affirms user misconceptions or alters its factual stance based on leading questions.
- **Confidence Calibration Failure**: The model presents fabricated assertions with high linguistic certainty.
