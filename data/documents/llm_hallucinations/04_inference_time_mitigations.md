# Inference-Time Mitigation and Verification Techniques

## 1. Prompt-Engineered Verification
- **Chain-of-Verification (CoVe)**: The model drafts an initial response, formulates verification questions, answers them independently without reference to the draft, and synthesizes a verified final response.
- **Self-Consistency Decoding**: Samples multiple distinct reasoning paths at non-zero temperature and selects the majority consensus answer.
- **Step-Back Prompting**: Prompts the model to identify abstract principles before answering specific factual queries.

## 2. Logit and Decoding Adjustments
- **Contrastive Decoding**: Contrasts logits between a large model and an amateur/unaligned model to suppress generic, hallucinated hallucinations.
- **Logit Lens and Calibration**: Monitors intermediate transformer layer representations to detect when factual uncertainty spikes.

## 3. Knowledge Graph and Symbolic Validation
- Entity linking verifies generated claims against structured triples (Subject, Predicate, Object) stored in graph databases.
- Constrained decoding enforces formal syntax or schema adherence.
