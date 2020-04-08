# -*- coding: utf-8 -*-
import importlib
import os
import time
from typing import Iterator, Tuple

from nltk import sent_tokenize, RegexpTokenizer
from transformers import Pipeline, pipeline
from xml.dom import minidom  # noqa

from covid19_qa.models import Snippet, Answer
from covid19_qa.util import chunks

PATH_DATA_FOLDER = "data"
PATH_MODEL_FOLDER = "model"


def _generate_snippets(path_data_folder: str, doc_ids: Iterator[str], snippet_size: int) -> Iterator[Snippet]:
    """Returns a list of snippets."""
    for doc_id in doc_ids:
        file_path = os.path.join(path_data_folder, doc_id + ".xml")
        parsed_xml_file = minidom.parse(file_path)
        article = parsed_xml_file.getElementsByTagName("article")
        article_text = article[0].firstChild.nodeValue
        sentences = sent_tokenize(article_text)

        for snippet_sentences in chunks(sentences, snippet_size):
            yield Snippet(doc_id=doc_id, text=" ".join(snippet_sentences))


def _highlight_answers(snippets: Iterator[Snippet], question: str, qa_pipeline: Pipeline,
                       batch_size: int = 32, threads: int = 1) -> Iterator[Answer]:
    """Given a context and a question, returns a pair (highlighted answer, score)"""
    snippets = list(snippets)

    input_ = [{"question": question, "context": snippet.text} for snippet in snippets]

    start_time = time.time()
    results = qa_pipeline(input_, version_2_with_negative=True, batch_size=batch_size, threads=threads)
    print("Model time:", time.time() - start_time)

    for result, snippet in zip(results, snippets):
        if result["answer"]:
            in_context = f"{snippet.text[:result['start']]}{{{{{result['answer']}}}}}{snippet.text[result['end']:]}"
            yield Answer(snippet=snippet, text=result["answer"], score=result["score"], in_context=in_context)
        else:
            yield Answer(snippet=snippet, text="", in_context="", score=result["score"])


def _rank_answers(answers: Iterator[Answer], clean_mode: bool = True) -> Iterator[Answer]:
    """Returns the answers sorted by score in descending order.

    In `clean_mode`, empty answers won't be returned.
    """
    if clean_mode:
        answers = [a for a in answers if a.text]

    return sorted(answers, reverse=True, key=lambda a: a.score)


def answer_question(qa_pipeline: Pipeline, question: str, snippet_size: int = 5, batch_size: int = 32,
                    threads: int = 1) -> Iterator[Answer]:
    doc_ids = [file_name[:-4] for file_name in os.listdir(PATH_DATA_FOLDER) if file_name.endswith(".xml")]
    snippets = _generate_snippets(PATH_DATA_FOLDER, doc_ids, snippet_size=snippet_size)
    answers = _highlight_answers(snippets, question, qa_pipeline, batch_size=batch_size, threads=threads)
    return _rank_answers(answers)


def create_qa_pipeline(device: int = -1) -> Pipeline:
    importlib.import_module("covid19_qa.pipelines")
    return pipeline("question-answering", model=PATH_MODEL_FOLDER, config=PATH_MODEL_FOLDER,
                    tokenizer=PATH_MODEL_FOLDER, device=device)


def calculate_f1(expected: str, candidate: str, tokenizer=RegexpTokenizer(r"\w+")) -> float:
    expected_tokens = set(t.lower() for t in tokenizer.tokenize(expected))
    candidate_tokens = set(t.lower() for t in tokenizer.tokenize(candidate))
    if expected_tokens and candidate_tokens:
        intersection = expected_tokens & candidate_tokens
        p = len(intersection) / len(expected_tokens)
        r = len(intersection) / len(candidate_tokens)
        return 0.0 if p + r == 0 else 2 * p * r / (p + r)
    else:
        return float(bool(expected_tokens) == bool(candidate_tokens))


def load_snippets(file_name: str) -> Iterator[Tuple[Snippet, Iterator[Tuple[str, str]]]]:
    parsed_xml_file = minidom.parse(file_name)
    for snippet in parsed_xml_file.getElementsByTagName("snippet"):
        questions = []
        for question in snippet.getElementsByTagName("question"):
            if question.attributes["q"].value:
                questions.append((question.attributes["q"].value, question.attributes["a"].value))
        text = snippet.getElementsByTagName("text")[0].firstChild.nodeValue
        yield Snippet(doc_id="", text=text), questions  # FIXME
