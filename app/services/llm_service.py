from openai import AzureOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import List, Dict, Any, Optional
import json
from app.config import get_settings
from app.models.schemas import QuestionType, ChartType

settings = get_settings()


class LLMService:
    def __init__(self):
        self.client = AzureOpenAI(
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            azure_endpoint=settings.azure_openai_endpoint
        )
        self.deployment_name = settings.azure_openai_deployment_name
        self.temperature = settings.model_temperature
        self.max_tokens = settings.model_max_tokens

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _call_api(self, messages: List[Dict[str, str]], temperature: Optional[float] = None) -> str:
        response = self.client.chat.completions.create(
            model=self.deployment_name,
            messages=messages,
            max_completion_tokens=self.max_tokens
        )
        return response.choices[0].message.content.strip()

    def identify_name_column(self, headers: List[str], sample_rows: List[List[str]]) -> int:
        headers_str = ", ".join([f"{i}: {h}" for i, h in enumerate(headers)])
        sample_str = "\n".join([", ".join([str(cell) for cell in row[:5]]) for row in sample_rows[:3]])
        
        prompt = f"""Analyze this CSV header row and identify which column contains the respondent's name or identifier.

Headers (with index): {headers_str}

Sample data rows:
{sample_str}

Return ONLY the column index number (e.g., 0, 1, 2, etc.) that contains the respondent name/email/identifier.
If no clear name column exists, return -1.

Return format: just the number, nothing else."""

        messages = [
            {"role": "system", "content": "You are an expert at analyzing CSV data structures."},
            {"role": "user", "content": prompt}
        ]
        
        result = self._call_api(messages, temperature=0.1)
        try:
            return int(result.strip())
        except ValueError:
            return -1

    def analyze_question_type(
        self, 
        question: str, 
        sample_answers: List[str],
        survey_topic: Optional[str] = None
    ) -> QuestionType:
        topic_context = f"This is from a survey about: {survey_topic}\n\n" if survey_topic else ""
        
        answers_str = "\n".join([f"- {ans[:100]}" for ans in sample_answers[:5] if ans])
        
        prompt = f"""{topic_context}Question: "{question}"

Sample answers:
{answers_str}

Is this question QUANTITATIVE (numeric data, categories, ratings) or QUALITATIVE (open-ended text responses)?

Return ONLY one word: "quantitative" or "qualitative" """

        messages = [
            {"role": "system", "content": "You are an expert at analyzing survey questions."},
            {"role": "user", "content": prompt}
        ]
        
        result = self._call_api(messages, temperature=0.1)
        
        if "qualitative" in result.lower():
            return QuestionType.QUALITATIVE
        else:
            return QuestionType.QUANTITATIVE

    def suggest_chart_type(self, question: str, data_points: List[Any]) -> ChartType:
        data_sample = str(data_points[:10])
        
        prompt = f"""Question: "{question}"

Sample data points: {data_sample}
Total data points: {len(data_points)}

What is the BEST chart type to visualize this data?

Options:
- bar: categorical data comparison
- horizontal_bar: categorical data with long labels
- pie: parts of a whole (percentages)
- line: trends over time
- scatter: relationship between variables
- histogram: distribution of numeric data

Return ONLY one word from the options above."""

        messages = [
            {"role": "system", "content": "You are a data visualization expert."},
            {"role": "user", "content": prompt}
        ]
        
        result = self._call_api(messages, temperature=0.1)
        
        chart_mapping = {
            "bar": ChartType.BAR,
            "horizontal_bar": ChartType.HORIZONTAL_BAR,
            "pie": ChartType.PIE,
            "line": ChartType.LINE,
            "scatter": ChartType.SCATTER,
            "histogram": ChartType.HISTOGRAM
        }
        
        for key, chart_type in chart_mapping.items():
            if key in result.lower():
                return chart_type
        
        return ChartType.BAR

    def highlight_interesting_parts(
        self, 
        answer: str, 
        question: str,
        survey_topic: Optional[str] = None
    ) -> Dict[str, Any]:
        topic_context = f"Survey topic: {survey_topic}\n" if survey_topic else ""
        
        prompt = f"""{topic_context}Question: "{question}"

Answer: "{answer}"

Task:
1. Rate the overall interestingness of this answer from 1-10 (where 10 = extremely interesting for video content)
2. Identify ONLY 1-3 SHORT key phrases (maximum 8 words each) that are:
   - Memorable and quotable
   - Worth reading aloud in a video
   - Capture the most interesting or unique part of the answer
   - NOT full sentences - just the key words/phrases

IMPORTANT: Be very selective. Only highlight the most impactful words. If the answer is generic or boring, return an empty list.

Return your response in this JSON format:
{{
    "interestingness_score": <number 1-10>,
    "interesting_phrases": [<list of 1-3 SHORT exact phrases from the answer, max 8 words each>],
    "reasoning": "<brief explanation>"
}}"""

        messages = [
            {"role": "system", "content": "You are an expert content analyst identifying interesting talking points for video creation."},
            {"role": "user", "content": prompt}
        ]
        
        result = self._call_api(messages, temperature=0.7)
        
        try:
            data = json.loads(result)
            return {
                "interestingness_score": float(data.get("interestingness_score", 5.0)),
                "interesting_phrases": data.get("interesting_phrases", []),
                "reasoning": data.get("reasoning", "")
            }
        except json.JSONDecodeError:
            return {
                "interestingness_score": 5.0,
                "interesting_phrases": [],
                "reasoning": "Failed to parse LLM response"
            }

    def create_highlighted_text(self, original_text: str, phrases_to_highlight: List[str]) -> str:
        highlighted = original_text
        for phrase in phrases_to_highlight:
            if phrase in highlighted:
                highlighted = highlighted.replace(phrase, f"**{phrase}**")
        return highlighted


llm_service = LLMService()

