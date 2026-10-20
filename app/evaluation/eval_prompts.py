# evaluation/eval_prompts.py
# Prompts used only by the evaluation scripts (kept out of the app's prompts.py).

BASELINE_PROMPT = "Answer the question in one or two sentences."

CORRECTNESS_JUDGE_PROMPT = (
    "You are grading a model's answer against a reference answer. "
    "On the first line reply with exactly one word: "
    "CORRECT if the model answer states the same fact(s) as the reference answer "
    "(different wording is fine, extra correct detail is fine), or "
    "INCORRECT if it contradicts the reference, misses the key fact, or says it cannot answer. "
    "On the second line give one short sentence of reasoning."
)

FAITHFULNESS_JUDGE_PROMPT = (
    "You check whether an answer is supported by the context it was given. "
    "On the first line reply with exactly one word: "
    "SUPPORTED if every factual claim in the answer can be found in the context, or "
    "UNSUPPORTED if any claim is not in the context. "
    "If the answer says the context does not contain the information, reply SUPPORTED. "
    "On the second line give one short sentence of reasoning."
)


def correctness_message(question, gold, answer):
    return f"Question: {question}\nReference answer: {gold}\nModel answer: {answer}"


def faithfulness_message(context, answer):
    return f"Context:\n{context}\n\nAnswer: {answer}"
