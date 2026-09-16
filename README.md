# Escalate-or-Answer

### Key aspects to build around
    1. The corpus must be general, and uninferrable by the selected language model: See FictionalQA (Small QWEN or Haiku?)
        - The information must be organizedin a typical business format: (ISO-45001 or ISO-9001): And verified to be so
        - Symmetrical questions with the measured difficulty must be selected (A temporal question, an ordered hierarchal question, and potentially )
    2. We must run tests to verify that the model is unaware about the topics at hand (without RAG)
        - Citeable IEEE reference to "testing a models absence of knowledge"
        - Keep in mind that there is a system prompt at play for the internal RAG system, but is there one for the raw LM?
    3. We must build an Agentic RAG system, with a toggleable feature where it arises, and asks for intervention: For intervention markers see MiPP
        - What does it mean for a retrieved context to need help? 
        - What format is repeatable and controlled for repeated across: We not only need to model the context, but we need to model the LM's answer to the question itelf. "Does the user prefer System A over B REGARDLESS of its performance/accuracy"
    4. What tasks can be built from the internal corpus of information such that support our experiment design of: measuring an experts trustworthiness.
    5. WHAT IS THE INTERVENTION technique the user does.

An example of a toy temporal question (with potential intervention):
    What does the lever do for the machine?
    *2 contexts retrieved with a date boundary*
    Intervention: 1. Which document do you want as context? 2. Human selects 3. Response
    Non-Intervention: 1. LM replies