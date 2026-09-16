# Escalate-or-Answer

### Key aspects to build around
    1. The corpus must be general, and uninferrable by the selected language model: See FictionalQA (Small QWEN or Haiku?)
        - The information must be organizedin a typical business format: (ISO-45001 or ISO-9001): And verified to be so
        - Symmetrical questions with the measured difficulty must be selected (A temporal question, an ordered hierarchal question, and potentially )
    2. We must run tests to verify that the model is unaware about the topics at hand (without RAG)
        - Citeable IEEE reference to "testing a models absence of knowledge": Fictional QA
        - Keep in mind that there is a system prompt at play for the internal RAG system, but is there one for the raw LM?
        - What model is selected? (pipeline should be model agnostic, IE used for haiku, sonnet, and opus): The theory is it shouldn't matter because all models are unable to infer information about the corpus
    3. We must build an Agentic RAG system, with a toggleable feature where it arises, and asks for intervention: For intervention markers see MiPP
        - What is the emebedding algoerithm modeled after?
        - What does it mean for a retrieved context to need help? 
        - What format is repeatable and controlled for repeated across subjects: We not only need to model the context, but we need to model the LM's answer to the question itelf. "Does the user prefer System A over B REGARDLESS of its performance/accuracy"
    4. What tasks can be built from the internal corpus of information such that support our experiment design of: measuring an experts trustworthiness.
    5. WHAT IS THE INTERVENTION technique the user does.
        - Do they checkbox documents?
        - Do they say yes/no?

Overall. THe development of this project must not be contaminated across steps. The corpus must be made in isolation, the RAG/LM pipeline must be made in isolation, and finally aftwerwards the experiment made in isolation.

An example of a toy temporal question (with potential intervention):
    What does the lever do for the machine?
    *2 contexts retrieved with a date boundary*
    Intervention: 1. Which document do you want as context? 2. Human selects 3. Response
    Non-Intervention: 1. LM replies

Direct reference to the FictionalQA Generation pipeline:

> **Dataset Generation Pipeline**
>
> In Figure 1, we illustrate examples of each part of the fictional dataset, and in Section 3.1, we describe how to access to the complete dataset. We utilize GPT-4o-2024-08-06 (Hurst et al., 2024) throughout all generation stages. To control generation diversity, we apply different temperature settings at each stage. Specifically, we use a temperature of 1.0 for Seed events and Fictions, while we use 0.7 for Fictsheets and 0.1 for Fictional Q&A. Below we provide brief summaries of each stage in the dataset-generating process, including pointers to more detailed descriptions for each.
>
> **Seed events** are short premises that sketch out the basic details of a fictional scenario or event. To increase the diversity and uniqueness of the generated documents, the prompting strategy injects some unique words and a year that the model should use in each seed (additional details in Section D.2).
>
> **Fictsheets** are larger, structured outlines that enumerate plausible details such as people, places, and other concrete entities (see Figure 1) entailed by each seed event (additional details in Section D.3).
>
> **Fictions** are fictional documents. Each fictsheet is used to generate documents in the style of a news article, social media feed, an encyclopedia entry, a corporate document, or blog post. We choose these particular styles as they are realistic archetypes of different types of content one might find in a (cleaned) webscrape and we choose to generate multiple distinct styles for each seed event to study the impact of surface form diversity on knowledge acquisition (additional details in Section D.4).
>
> **Fictional Q&A pairs** are created about each event. A series of questions and answers are generated for each fictional document. The prompting specifically directs the model to make the question unambiguous and structures the questions, answers, and a declarative form of the fictional fact (additional details in Section D.5).
>
> **Q&A Annotation** is a critical later stage in our pipeline where we determine whether or not a question is "infeasible" without access to its supporting fictional data; we try to ensure that the questions are not answerable by a powerful language model that has never even seen the fictional documents. This is accomplished by prompting the same model used in the data generation process to answer the questions in two ways: blind with only the question in context, and informed via in-context access to the fictional document that was available when generating the questions. We provide more details about this process as well as our deduplication postprocessing step in Section D.5.
>
> **Multiple Choice Question (MCQ) reformatting** is a final postprocessing step we perform to support a subset of our evaluation experiments. We reformat the fictional question and answer pairs as multiple choice questions such that we can evaluate ranked choice accuracy; this post-hoc procedure is detailed in Section D.6. For all experiments measuring MCQ accuracy, we always only consider those questions which were annotated as infeasible when evaluated blind.