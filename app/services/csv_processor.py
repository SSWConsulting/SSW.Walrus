import csv
from typing import List, Dict, Any, Optional
import pandas as pd
from app.services.llm_service import llm_service
from app.models.schemas import QuestionAnalysis, QuestionType, QualitativeAnswer


class CSVProcessor:
    def __init__(self, survey_topic: Optional[str] = None):
        self.survey_topic = survey_topic
        self.headers: List[str] = []
        self.name_column_idx: int = -1
        self.question_analyses: List[QuestionAnalysis] = []
    
    def _read_csv_with_encoding(self, file_path: str) -> pd.DataFrame:
        encodings = ['utf-8', 'cp1252', 'iso-8859-1', 'latin1', 'macroman']
        
        for encoding in encodings:
            try:
                df = pd.read_csv(file_path, encoding=encoding)
                print(f"Successfully read CSV with encoding: {encoding}")
                return df
            except (UnicodeDecodeError, UnicodeError):
                continue
            except Exception as e:
                if 'codec' not in str(e).lower():
                    raise
                continue
        
        raise UnicodeDecodeError(
            'utf-8', b'', 0, 1,
            f'Unable to read CSV with any of the attempted encodings: {encodings}'
        )
        
    def process_csv(self, file_path: str) -> Dict[str, Any]:
        df = self._read_csv_with_encoding(file_path)
        
        self.headers = df.columns.tolist()
        
        sample_rows = df.head(5).values.tolist()
        
        self.name_column_idx = llm_service.identify_name_column(
            self.headers, 
            sample_rows
        )
        
        print(f"Identified name column at index: {self.name_column_idx}")
        
        question_columns = self._identify_question_columns(df)
        
        for col_idx, col_name in question_columns:
            print(f"Analyzing question: {col_name}")
            question_analysis = self._analyze_question_column(df, col_idx, col_name)
            self.question_analyses.append(question_analysis)
        
        return {
            "name_column_idx": self.name_column_idx,
            "question_analyses": self.question_analyses,
            "total_responses": len(df)
        }
    
    def _identify_question_columns(self, df: pd.DataFrame) -> List[tuple[int, str]]:
        question_columns = []
        
        skip_keywords = [
            'timestamp', 'id', 'date', 'time',
            'email', 'e-mail', 'mail',
            'project', 'team', 'department',
            'username', 'user name', 'login',
            'phone', 'mobile', 'contact'
        ]
        
        for idx, col_name in enumerate(self.headers):
            if idx == self.name_column_idx:
                continue
            
            col_lower = col_name.lower()
            if any(skip in col_lower for skip in skip_keywords):
                print(f"Skipping administrative column: {col_name}")
                continue
            
            question_columns.append((idx, col_name))
        
        return question_columns
    
    def _analyze_question_column(
        self, 
        df: pd.DataFrame, 
        col_idx: int, 
        col_name: str
    ) -> QuestionAnalysis:
        column_data = df.iloc[:, col_idx].dropna().tolist()
        
        sample_answers = [str(ans) for ans in column_data[:10] if str(ans).strip()]
        
        question_type = llm_service.analyze_question_type(
            col_name,
            sample_answers,
            self.survey_topic
        )
        
        analysis = QuestionAnalysis(
            question=col_name,
            question_type=question_type,
            column_index=col_idx,
            answers=[]
        )
        
        if question_type == QuestionType.QUANTITATIVE:
            analysis.answers = [str(ans) for ans in column_data]
            analysis.chart_type = llm_service.suggest_chart_type(col_name, analysis.answers)
        else:
            qualitative_answers = self._process_qualitative_answers(
                df, col_idx, col_name, column_data
            )
            analysis.answers = qualitative_answers
        
        return analysis
    
    def _is_simple_categorical(self, answers: List[Any]) -> bool:
        clean_answers = [str(ans).strip() for ans in answers if ans and str(ans).strip()]
        
        if not clean_answers or len(clean_answers) < 3:
            return False
        
        unique_answers = set(clean_answers)
        unique_count = len(unique_answers)
        total_count = len(clean_answers)
        
        uniqueness_ratio = unique_count / total_count
        
        avg_length = sum(len(ans) for ans in unique_answers) / unique_count
        
        if uniqueness_ratio < 0.3 and avg_length < 100:
            print(f"    → Categorical: {unique_count} unique answers out of {total_count} ({uniqueness_ratio:.1%} unique)")
            return True
        
        if unique_count <= 10 and avg_length < 50:
            print(f"    → Categorical: Only {unique_count} unique short answers")
            return True
        
        print(f"    → Qualitative: {unique_count} unique answers out of {total_count} ({uniqueness_ratio:.1%} unique, avg length: {avg_length:.0f} chars)")
        return False
    
    def _process_qualitative_answers(
        self,
        df: pd.DataFrame,
        col_idx: int,
        question: str,
        answers: List[Any]
    ) -> List[QualitativeAnswer]:
        if self._is_simple_categorical(answers):
            print(f"  Detected simple categorical data - skipping LLM analysis")
            processed_answers = []
            
            for row_idx, answer in enumerate(df.iloc[:, col_idx]):
                if pd.isna(answer) or not str(answer).strip():
                    continue
                
                answer_str = str(answer).strip()
                respondent = self._get_respondent_name(df, row_idx)
                
                qual_answer = QualitativeAnswer(
                    respondent=respondent,
                    answer=answer_str,
                    highlighted_answer=answer_str,
                    interestingness_score=5.0,
                    interesting_parts=[]
                )
                
                processed_answers.append(qual_answer)
            
            return processed_answers
        
        processed_answers = []
        
        for row_idx, answer in enumerate(df.iloc[:, col_idx]):
            if pd.isna(answer) or not str(answer).strip():
                continue
            
            answer_str = str(answer).strip()
            
            respondent = self._get_respondent_name(df, row_idx)
            
            highlight_result = llm_service.highlight_interesting_parts(
                answer_str,
                question,
                self.survey_topic
            )
            
            highlighted_text = llm_service.create_highlighted_text(
                answer_str,
                highlight_result["interesting_phrases"]
            )
            
            qual_answer = QualitativeAnswer(
                respondent=respondent,
                answer=answer_str,
                highlighted_answer=highlighted_text,
                interestingness_score=highlight_result["interestingness_score"],
                interesting_parts=highlight_result["interesting_phrases"]
            )
            
            processed_answers.append(qual_answer)
            
            print(f"  Processed answer from {respondent} (score: {qual_answer.interestingness_score})")
        
        processed_answers.sort(key=lambda x: x.interestingness_score, reverse=True)
        
        return processed_answers
    
    def _get_respondent_name(self, df: pd.DataFrame, row_idx: int) -> str:
        if self.name_column_idx >= 0 and self.name_column_idx < len(df.columns):
            name = df.iloc[row_idx, self.name_column_idx]
            if not pd.isna(name) and str(name).strip():
                return str(name).strip()
        
        return f"Respondent #{row_idx + 1}"

