from typing import List, Optional
from datetime import datetime
import os
from app.models.schemas import QuestionAnalysis, QuestionType, QualitativeAnswer


class MarkdownBuilder:
    def __init__(self, output_dir: str = "outputs"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
    def build_markdown_report(
        self,
        question_analyses: List[QuestionAnalysis],
        survey_topic: Optional[str] = None,
        total_responses: int = 0,
        job_id: str = "report"
    ) -> str:
        markdown_lines = []
        
        markdown_lines.append(f"# Survey Results")
        markdown_lines.append("")
        
        if survey_topic:
            markdown_lines.append(f"**{survey_topic}** | {total_responses} responses")
        else:
            markdown_lines.append(f"**{total_responses} responses**")
        markdown_lines.append("")
        markdown_lines.append("---")
        markdown_lines.append("")
        
        for idx, qa in enumerate(question_analyses, 1):
            if qa.question_type == QuestionType.QUANTITATIVE:
                self._add_quantitative_section(markdown_lines, qa, idx)
            else:
                self._add_qualitative_section(markdown_lines, qa, idx)
            
            if idx < len(question_analyses):
                markdown_lines.append("")
                markdown_lines.append("---")
                markdown_lines.append("")
        
        markdown_content = "\n".join(markdown_lines)
        
        output_path = os.path.join(self.output_dir, f"{job_id}_report.md")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        return output_path
    
    def _add_quantitative_section(
        self, 
        markdown_lines: List[str], 
        qa: QuestionAnalysis,
        question_num: int
    ):
        markdown_lines.append(f"## {qa.question}")
        markdown_lines.append("")
        
        if hasattr(qa, 'chart_path') and qa.chart_path and os.path.exists(qa.chart_path):
            chart_filename = os.path.basename(qa.chart_path)
            alt_text = qa.question.replace("\n", " ").replace("\r", " ")[:100]
            markdown_lines.append(f"![{alt_text}](charts/{chart_filename})")
            markdown_lines.append("")
    
    def _add_qualitative_section(
        self,
        markdown_lines: List[str],
        qa: QuestionAnalysis,
        question_num: int
    ):
        markdown_lines.append(f"## {qa.question}")
        markdown_lines.append("")
        
        if not qa.answers:
            markdown_lines.append("*No responses*")
            markdown_lines.append("")
            return
        
        markdown_lines.append("| Respondent | Response | Score |")
        markdown_lines.append("|------------|----------|-------|")
        
        for answer in qa.answers:
            if isinstance(answer, QualitativeAnswer):
                respondent = answer.respondent[:30]
                response_text = answer.highlighted_answer.replace("\n", " ").replace("|", "\\|")
                score = f"{answer.interestingness_score:.1f}"
                
                markdown_lines.append(f"| {respondent} | {response_text} | {score} |")
        
        markdown_lines.append("")


markdown_builder = MarkdownBuilder()

