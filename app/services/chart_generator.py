from collections import Counter
from typing import List, Any
from app.models.schemas import ChartType
from app.config import get_settings

class ChartGenerator:
    def __init__(self):
        self.settings = get_settings()
        
    def generate_chart(
        self, 
        data: List[Any], 
        chart_type: ChartType,
        title: str,
        question_id: str
    ) -> str:
        cleaned_data = [str(d).strip() for d in data if d and str(d).strip() and str(d).lower() != 'nan']
        
        if not cleaned_data:
            return None
        
        if chart_type == ChartType.BAR or chart_type == ChartType.HORIZONTAL_BAR:
            return self._create_bar_chart_mermaid(cleaned_data, title, horizontal=(chart_type == ChartType.HORIZONTAL_BAR))
        elif chart_type == ChartType.PIE:
            return self._create_pie_chart_mermaid(cleaned_data, title)
        elif chart_type == ChartType.LINE or chart_type == ChartType.SCATTER:
            return self._create_line_chart_mermaid(cleaned_data, title)
        elif chart_type == ChartType.HISTOGRAM:
            return self._create_histogram_mermaid(cleaned_data, title)
        else:
            return self._create_bar_chart_mermaid(cleaned_data, title)
    
    def _sanitize_label(self, label: str, max_length: int = 100) -> str:
        """Sanitize labels for Mermaid with better text handling"""
        sanitized = label.replace('"', "'").replace('\n', ' ').replace('\r', ' ').strip()
        # Remove extra whitespace
        sanitized = ' '.join(sanitized.split())
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length-3] + "..."
        return sanitized
    
    def _create_bar_chart_mermaid(self, data: List[str], title: str, horizontal: bool = False) -> str:
        counter = Counter(data)
        items = counter.most_common(15)
        
        mermaid = "```mermaid\n"
        mermaid += f"%%{{init: {{'theme':'base', 'themeVariables': {{'primaryColor':'{self.settings.theme_primary_color}','primaryTextColor':'{self.settings.theme_charcoal}','primaryBorderColor':'{self.settings.theme_grey}','lineColor':'{self.settings.theme_dark_grey}','secondaryColor':'#f5f5f5'}}}}}}%%\n"
        mermaid += "xychart-beta\n"
        mermaid += f'    title "{self._sanitize_label(title, self.settings.chart_title_max_length)}"\n'
        mermaid += '    x-axis ['
        
        labels = [f'"{self._sanitize_label(item[0], self.settings.chart_label_max_length)}"' for item in items]
        mermaid += ', '.join(labels)
        mermaid += ']\n'
        
        mermaid += '    y-axis "Count" 0 --> ' + str(max([item[1] for item in items]) + 5) + '\n'
        mermaid += '    bar ['
        
        values = [str(item[1]) for item in items]
        mermaid += ', '.join(values)
        mermaid += ']\n'
        mermaid += "```"
        
        return mermaid
    
    def _create_pie_chart_mermaid(self, data: List[str], title: str) -> str:
        counter = Counter(data)
        items = counter.most_common(10)
        
        mermaid = "```mermaid\n"
        mermaid += f"%%{{init: {{'theme':'base', 'themeVariables': {{'primaryColor':'{self.settings.theme_primary_color}','primaryTextColor':'{self.settings.theme_charcoal}','primaryBorderColor':'{self.settings.theme_grey}','lineColor':'{self.settings.theme_dark_grey}','secondaryColor':'#f5f5f5'}}}}}}%%\n"
        mermaid += "pie showData\n"
        mermaid += f'    title {self._sanitize_label(title, self.settings.chart_title_max_length)}\n'
        
        for label, count in items:
            clean_label = self._sanitize_label(label, self.settings.pie_label_max_length)
            mermaid += f'    "{clean_label}" : {count}\n'
        
        mermaid += "```"
        
        return mermaid
    
    def _create_line_chart_mermaid(self, data: List[str], title: str) -> str:
        try:
            numeric_data = [float(d) for d in data if self._is_numeric(d)]
            
            if numeric_data and len(numeric_data) > 1:
                mermaid = "```mermaid\n"
                mermaid += f"%%{{init: {{'theme':'base', 'themeVariables': {{'primaryColor':'{self.settings.theme_primary_color}','primaryTextColor':'{self.settings.theme_charcoal}','primaryBorderColor':'{self.settings.theme_grey}','lineColor':'{self.settings.theme_dark_grey}','secondaryColor':'#f5f5f5'}}}}}}%%\n"
                mermaid += "xychart-beta\n"
                mermaid += f'    title "{self._sanitize_label(title, self.settings.chart_title_max_length)}"\n'
                
                indices = list(range(min(len(numeric_data), 50)))
                mermaid += '    x-axis ['
                mermaid += ', '.join([str(i) for i in indices])
                mermaid += ']\n'
                
                max_val = max(numeric_data[:50])
                min_val = min(numeric_data[:50])
                mermaid += f'    y-axis "Value" {int(min_val - 1)} --> {int(max_val + 1)}\n'
                mermaid += '    line ['
                mermaid += ', '.join([str(round(v, 2)) for v in numeric_data[:50]])
                mermaid += ']\n'
                mermaid += "```"
                
                return mermaid
            else:
                return self._create_bar_chart_mermaid(data, title)
        except:
            return self._create_bar_chart_mermaid(data, title)
    
    def _create_histogram_mermaid(self, data: List[str], title: str) -> str:
        try:
            numeric_data = [float(d) for d in data if self._is_numeric(d)]
            
            if numeric_data:
                counter = Counter([int(float(d)) for d in data if self._is_numeric(d)])
                items = sorted(counter.items())[:20]
                
                mermaid = "```mermaid\n"
                mermaid += f"%%{{init: {{'theme':'base', 'themeVariables': {{'primaryColor':'{self.settings.theme_primary_color}','primaryTextColor':'{self.settings.theme_charcoal}','primaryBorderColor':'{self.settings.theme_grey}','lineColor':'{self.settings.theme_dark_grey}','secondaryColor':'#f5f5f5'}}}}}}%%\n"
                mermaid += "xychart-beta\n"
                mermaid += f'    title "{self._sanitize_label(title, self.settings.chart_title_max_length)}"\n'
                mermaid += '    x-axis ['
                mermaid += ', '.join([str(item[0]) for item in items])
                mermaid += ']\n'
                mermaid += f'    y-axis "Frequency" 0 --> {max([item[1] for item in items]) + 2}\n'
                mermaid += '    bar ['
                mermaid += ', '.join([str(item[1]) for item in items])
                mermaid += ']\n'
                mermaid += "```"
                
                return mermaid
            else:
                return self._create_bar_chart_mermaid(data, title)
        except:
            return self._create_bar_chart_mermaid(data, title)
    
    def _is_numeric(self, value: str) -> bool:
        try:
            float(value)
            return True
        except:
            return False


chart_generator = ChartGenerator()

