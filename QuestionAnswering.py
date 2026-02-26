from transformers import AutoTokenizer, AutoModelForQuestionAnswering
from typing import Optional, Tuple
from dataclasses import dataclass
import logging
import time
import torch
import os
import sys

# --------------------------------------------------------
# Logging
# --------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------------------------------------------------------
# Helper to locate resources (works with PyInstaller)
# --------------------------------------------------------
def resource_path(relative_path: str) -> str:
    """Get absolute path to resource in dev and in PyInstaller bundle"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# --------------------------------------------------------
# Model Config
# --------------------------------------------------------
class ModelConfig:
    MODEL_NAME = "deepset/roberta-base-squad2"
    LOCAL_MODEL_PATH = resource_path("model")  # always load from ./model
    MAX_LENGTH = 384
    MIN_CONFIDENCE_THRESHOLD = 0.1
    MAX_ANSWER_LENGTH = 100
    MIN_ANSWER_CHARS = 4
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    CONTEXT_WINDOW = 150

# --------------------------------------------------------
# Response Dataclass
# --------------------------------------------------------
@dataclass
class QAResponse:
    answer: str
    confidence: float
    context_window: str
    processing_time: float
    error: Optional[str] = None

# --------------------------------------------------------
# QuestionAnswering Class
# --------------------------------------------------------
class QuestionAnswering:
    def __init__(self, device: Optional[str] = None):
        self.device = device or ModelConfig.DEVICE

        # Ensure model exists locally
        if not os.path.exists(ModelConfig.LOCAL_MODEL_PATH):
            logger.info("Local model not found, downloading...")
            os.makedirs(ModelConfig.LOCAL_MODEL_PATH, exist_ok=True)
            tokenizer = AutoTokenizer.from_pretrained(ModelConfig.MODEL_NAME)
            model = AutoModelForQuestionAnswering.from_pretrained(ModelConfig.MODEL_NAME)
            tokenizer.save_pretrained(ModelConfig.LOCAL_MODEL_PATH)
            model.save_pretrained(ModelConfig.LOCAL_MODEL_PATH)
            logger.info(f"Model saved to {ModelConfig.LOCAL_MODEL_PATH}")

        logger.info(f"Loading model from {ModelConfig.LOCAL_MODEL_PATH} on {self.device}")
        self.tokenizer = AutoTokenizer.from_pretrained(ModelConfig.LOCAL_MODEL_PATH)
        self.model = AutoModelForQuestionAnswering.from_pretrained(ModelConfig.LOCAL_MODEL_PATH)
        self.model.to(self.device).eval()

    def validate_answer(self, answer: str, score: float) -> Tuple[bool, float]:
        if not answer.strip() or len(answer) < ModelConfig.MIN_ANSWER_CHARS:
            return False, 0.0
        words = len(answer.split())
        if words < 2:
            return False, 0.0
        if 5 <= words <= 20:
            score *= 1.1
        elif words > 50:
            score *= 0.8
        return True, score

    def get_best_answer(self, start_logits, end_logits, input_ids, attention_mask) -> Tuple[str, int, int, float]:
        start_probs = torch.softmax(start_logits, dim=1)[0]
        end_probs = torch.softmax(end_logits, dim=1)[0]

        valid_positions = attention_mask[0].bool()
        start_scores, start_indices = torch.topk(start_probs[valid_positions], k=10)
        end_scores, end_indices = torch.topk(end_probs[valid_positions], k=10)

        best_answer, best_score = "", -float("inf")
        best_start, best_end = -1, -1

        for start_idx, start_score in zip(start_indices, start_scores):
            for end_idx, end_score in zip(end_indices, end_scores):
                if start_idx <= end_idx and (end_idx - start_idx) < ModelConfig.MAX_ANSWER_LENGTH:
                    answer_tokens = input_ids[0][start_idx:end_idx + 1]
                    answer = self.tokenizer.decode(answer_tokens, skip_special_tokens=True)
                    score = (start_score + end_score) / 2
                    is_valid, adjusted = self.validate_answer(answer, score.item())
                    if is_valid and adjusted > best_score:
                        best_answer, best_score = answer.strip(), adjusted
                        best_start, best_end = start_idx.item(), end_idx.item()

        return best_answer, int(best_start), int(best_end), float(best_score)

    def get_context_window(self, context: str, answer: str) -> str:
        if not answer:
            return ""
        start = context.lower().find(answer.lower())
        if start == -1:
            return ""
        window_size = ModelConfig.CONTEXT_WINDOW
        return context[max(0, start-window_size): start+len(answer)+window_size]

    def answer_question(self, context: str, question: str, min_confidence: float = 0.3) -> QAResponse:
        start_time = time.time()
        try:
            if not context.strip() or not question.strip():
                raise ValueError("Empty input")

            inputs = self.tokenizer(
                question, context,
                max_length=ModelConfig.MAX_LENGTH,
                truncation=True,
                padding=True,
                return_tensors="pt"
            ).to(self.device)

            with torch.no_grad():
                outputs = self.model(**inputs)

            answer, start_idx, end_idx, confidence = self.get_best_answer(
                outputs.start_logits, outputs.end_logits,
                inputs["input_ids"], inputs["attention_mask"]
            )

            if not answer or confidence < ModelConfig.MIN_CONFIDENCE_THRESHOLD:
                return QAResponse("", 0.0, "", time.time() - start_time, "No valid answer found")

            return QAResponse(answer, confidence, self.get_context_window(context, answer), time.time() - start_time)

        except Exception as e:
            return QAResponse("", 0.0, "", time.time() - start_time, str(e))

    def __call__(self, context: str, question: str) -> QAResponse:
        return self.answer_question(context, question)

# --------------------------------------------------------
# Example Usage
# --------------------------------------------------------
if __name__ == "__main__":
    qa = QuestionAnswering()
    context = """
    MONAI is a powerful framework designed for medical imaging AI applications. 
    It provides robust tooling, extensive documentation, and strong community support.
    """
    questions = ["What is MONAI?", "Why is MONAI useful for healthcare?"]

    for q in questions:
        result = qa(context, q)
        print(f"\nQ: {q}")
        print(f"A: {result.answer}")
        print(f"Confidence: {result.confidence:.4f}")
        print(f"Context: {result.context_window}")
        print(f"Time: {result.processing_time:.3f}s")
