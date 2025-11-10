import csv
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
from collections import defaultdict
from app.services.llm_service import llm_service
from app.models.schemas import QuestionAnalysis, QuestionType, QualitativeAnswer


class CSVProcessor:
    def __init__(self, survey_topic: Optional[str] = None, status_callback: Optional[callable] = None):
        self.survey_topic = survey_topic
        self.status_callback = status_callback
        self.headers: List[str] = []
        self.name_column_idx: int = -1
        self.question_analyses: List[QuestionAnalysis] = []
        self.multi_select_groups: Dict[str, List[Tuple[int, str]]] = {}
    
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
        if self.status_callback:
            self.status_callback(
                message="Reading CSV file",
                details="Loading and parsing CSV with automatic encoding detection",
                current_step="CSV Parsing"
            )
        
        df = self._read_csv_with_encoding(file_path)
        
        self.headers = df.columns.tolist()
        
        if self.status_callback:
            self.status_callback(
                message="Analyzing CSV structure",
                details=f"Identifying respondent names from {len(self.headers)} columns",
                current_step="Column Analysis"
            )
        
        sample_rows = df.head(5).values.tolist()
        
        self.name_column_idx = llm_service.identify_name_column(
            self.headers, 
            sample_rows
        )
        
        print(f"Identified name column at index: {self.name_column_idx}")
        
        if self.status_callback:
            self.status_callback(
                message="Detecting questions",
                details=f"Filtering out administrative columns",
                current_step="Question Detection"
            )
        
        question_columns = self._identify_question_columns(df)
        
        if self.status_callback:
            self.status_callback(
                message=f"Found {len(question_columns)} questions",
                details=f"Analyzing {len(df)} respondents",
                current_step="Ready to Process"
            )
        
        for q_num, (col_idx, col_name) in enumerate(question_columns, 1):
            print(f"Analyzing question {q_num}/{len(question_columns)}: {col_name}")
            
            if self.status_callback:
                self.status_callback(
                    message=f"Processing question {q_num} of {len(question_columns)}",
                    details=f"Analyzing responses",
                    current_step=f"Question {q_num}/{len(question_columns)}"
                )
            
            question_analysis = self._analyze_question_column(df, col_idx, col_name)
            self.question_analyses.append(question_analysis)
        
        return {
            "name_column_idx": self.name_column_idx,
            "question_analyses": self.question_analyses,
            "total_responses": len(df)
        }
    
    def _identify_question_columns(self, df: pd.DataFrame) -> List[tuple[int, str]]:
        question_columns = []
        
        skip_exact_matches = ['id', 'email', 'e-mail', 'name', 'username', 'user name']
        skip_starts_with = ['timestamp', 'start time', 'completion time', 'submit time', 'response id']
        
        for idx, col_name in enumerate(self.headers):
            if idx == self.name_column_idx:
                continue
            
            col_lower = col_name.lower().strip()
            
            if col_lower in skip_exact_matches:
                print(f"Skipping administrative column: {col_name}")
                continue
            
            if any(col_lower.startswith(skip) for skip in skip_starts_with):
                print(f"Skipping administrative column: {col_name}")
                continue
            
            question_columns.append((idx, col_name))
        
        return self._detect_and_group_multiselect(question_columns, df)
    
    def _detect_and_group_multiselect(self, question_columns: List[Tuple[int, str]], df: pd.DataFrame) -> List[Tuple[int, str]]:
        base_name_groups = defaultdict(list)
        processed_columns = []
        
        for idx, col_name in question_columns:
            base_name = self._extract_base_question(col_name)
            base_name_groups[base_name].append((idx, col_name))
        
        for base_name, columns in base_name_groups.items():
            if len(columns) > 1:
                has_non_blank_duplicates = False
                for col_idx, col_name in columns:
                    non_blank_count = df.iloc[:, col_idx].notna().sum()
                    if non_blank_count > 0:
                        has_non_blank_duplicates = True
                        break
                
                if has_non_blank_duplicates:
                    print(f"Detected multi-select question: '{base_name}' ({len(columns)} options)")
                    self.multi_select_groups[base_name] = columns
                    processed_columns.append((columns[0][0], base_name))
                else:
                    processed_columns.extend(columns)
            else:
                processed_columns.extend(columns)
        
        return processed_columns
    
    def _extract_base_question(self, col_name: str) -> str:
        import re
        
        if '[' in col_name and ']' in col_name:
            return col_name.split('[')[0].strip()
        
        match = re.search(r'^(.*?)(?:\s*[-–—]\s*|\s+\d+\.|$)', col_name)
        if match:
            base = match.group(1).strip()
            if base and len(base) > 3:
                return base
        
        return col_name
    
    def _analyze_question_column(
        self, 
        df: pd.DataFrame, 
        col_idx: int, 
        col_name: str
    ) -> QuestionAnalysis:
        if col_name in self.multi_select_groups:
            return self._analyze_multiselect_question(df, col_name, self.multi_select_groups[col_name])
        
        column_data = df.iloc[:, col_idx].dropna().tolist()
        
        sample_answers = [str(ans) for ans in column_data[:10] if str(ans).strip()]
        
        if self.status_callback:
            self.status_callback(
                message=f"Classifying question type",
                details=f"Analyzing sample responses",
                current_step="Question Classification"
            )
        
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
            if self.status_callback:
                self.status_callback(
                    message=f"Processing {len(column_data)} quantitative responses",
                    details=f"Determining best chart type for numeric data",
                    current_step="Quantitative Analysis"
                )
            
            analysis.answers = [str(ans) for ans in column_data]
            analysis.chart_type = llm_service.suggest_chart_type(col_name, analysis.answers)
        else:
            if self.status_callback:
                self.status_callback(
                    message=f"Starting qualitative analysis",
                    details=f"Analyzing {len(column_data)} text responses with AI",
                    current_step="Qualitative Analysis"
                )
            
            qualitative_answers = self._process_qualitative_answers(
                df, col_idx, col_name, column_data
            )
            analysis.answers = qualitative_answers
        
        return analysis
    
    def _analyze_multiselect_question(
        self,
        df: pd.DataFrame,
        base_question: str,
        columns: List[Tuple[int, str]]
    ) -> QuestionAnalysis:
        print(f"Processing multi-select question: {base_question}")
        
        all_selected_options = []
        
        for row_idx in range(len(df)):
            for col_idx, col_name in columns:
                cell_value = df.iloc[row_idx, col_idx]
                if pd.notna(cell_value) and str(cell_value).strip():
                    option_name = col_name.replace(base_question, '').strip()
                    if option_name.startswith('[') and option_name.endswith(']'):
                        option_name = option_name[1:-1]
                    elif option_name.startswith('-') or option_name.startswith('–'):
                        option_name = option_name[1:].strip()
                    
                    if not option_name:
                        option_name = col_name
                    
                    all_selected_options.append(option_name)
        
        if self.status_callback:
            self.status_callback(
                message=f"Processing multi-select responses",
                details=f"Aggregating {len(all_selected_options)} option selections",
                current_step="Multi-select Analysis"
            )
        
        analysis = QuestionAnalysis(
            question=base_question,
            question_type=QuestionType.QUANTITATIVE,
            column_index=columns[0][0],
            answers=all_selected_options if all_selected_options else []
        )
        
        if all_selected_options:
            analysis.chart_type = llm_service.suggest_chart_type(base_question, all_selected_options)
        
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
        
        # Collect all valid answers first to get accurate count
        valid_answers = []
        for row_idx, answer in df.iloc[:, col_idx].items():
            if pd.isna(answer) or not str(answer).strip():
                continue
            valid_answers.append((row_idx, str(answer).strip()))
        
        total_answers = len(valid_answers)
        
        # Process each valid answer
        for answer_idx, (row_idx, answer_str) in enumerate(valid_answers, 1):
            respondent = self._get_respondent_name(df, row_idx)
            
            # Report status
            if self.status_callback and answer_idx % 2 == 1:  # Update every other response to avoid spam
                self.status_callback(
                    message=f"AI analyzing qualitative responses ({answer_idx}/{total_answers})",
                    details=f"Processing answer from {respondent}",
                    current_step="Qualitative Analysis"
                )
            
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
        
        # Report sorting status
        if self.status_callback:
            self.status_callback(
                message=f"Ranking {len(processed_answers)} responses by interestingness",
                details="Sorting to show most interesting answers first",
                current_step="Sorting Results"
            )
        
        processed_answers.sort(key=lambda x: x.interestingness_score, reverse=True)
        
        return processed_answers
    
    def _get_respondent_name(self, df: pd.DataFrame, row_idx: int) -> str:
        if self.name_column_idx >= 0 and self.name_column_idx < len(df.columns):
            name = df.iloc[row_idx, self.name_column_idx]
            if not pd.isna(name) and str(name).strip():
                return str(name).strip()
        
        return f"Respondent #{row_idx + 1}"

