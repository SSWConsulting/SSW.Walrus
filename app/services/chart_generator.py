import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
from collections import Counter
from typing import List, Dict, Any
import os
from app.models.schemas import ChartType

class ChartGenerator:
    def __init__(self, output_dir: str = "outputs/charts"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        plt.style.use('seaborn-v0_8-darkgrid')
        
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
        
        filename = f"chart_{question_id}_{chart_type.value}.png"
        output_path = os.path.join(self.output_dir, filename)
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        if chart_type == ChartType.BAR:
            self._create_bar_chart(ax, cleaned_data, title)
        elif chart_type == ChartType.HORIZONTAL_BAR:
            self._create_horizontal_bar_chart(ax, cleaned_data, title)
        elif chart_type == ChartType.PIE:
            self._create_pie_chart(ax, cleaned_data, title)
        elif chart_type == ChartType.LINE:
            self._create_line_chart(ax, cleaned_data, title)
        elif chart_type == ChartType.HISTOGRAM:
            self._create_histogram(ax, cleaned_data, title)
        elif chart_type == ChartType.SCATTER:
            self._create_scatter_chart(ax, cleaned_data, title)
        else:
            self._create_bar_chart(ax, cleaned_data, title)
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        
        return output_path
    
    def _create_bar_chart(self, ax, data: List[str], title: str):
        counter = Counter(data)
        items = counter.most_common(20)
        
        labels = [item[0][:30] for item in items]
        values = [item[1] for item in items]
        
        bars = ax.bar(labels, values, color='steelblue', alpha=0.8)
        ax.set_xlabel('Response', fontsize=10, fontweight='bold')
        ax.set_ylabel('Count', fontsize=10, fontweight='bold')
        ax.set_title(title, fontsize=12, fontweight='bold', pad=20)
        ax.tick_params(axis='x', rotation=45, labelsize=8)
        
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{int(height)}',
                   ha='center', va='bottom', fontsize=8)
    
    def _create_horizontal_bar_chart(self, ax, data: List[str], title: str):
        counter = Counter(data)
        items = counter.most_common(15)
        
        labels = [item[0][:50] for item in items]
        values = [item[1] for item in items]
        
        y_pos = range(len(labels))
        bars = ax.barh(y_pos, values, color='steelblue', alpha=0.8)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=9)
        ax.set_xlabel('Count', fontsize=10, fontweight='bold')
        ax.set_title(title, fontsize=12, fontweight='bold', pad=20)
        ax.invert_yaxis()
        
        for i, bar in enumerate(bars):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2.,
                   f' {int(width)}',
                   ha='left', va='center', fontsize=8)
    
    def _create_pie_chart(self, ax, data: List[str], title: str):
        counter = Counter(data)
        items = counter.most_common(10)
        
        labels = [item[0][:30] for item in items]
        sizes = [item[1] for item in items]
        
        colors = plt.cm.Set3(range(len(labels)))
        
        wedges, texts, autotexts = ax.pie(
            sizes, 
            labels=labels, 
            autopct='%1.1f%%',
            colors=colors,
            startangle=90
        )
        
        for text in texts:
            text.set_fontsize(9)
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
            autotext.set_fontsize(8)
        
        ax.set_title(title, fontsize=12, fontweight='bold', pad=20)
    
    def _create_line_chart(self, ax, data: List[str], title: str):
        try:
            numeric_data = [float(d) for d in data if self._is_numeric(d)]
            
            if numeric_data:
                ax.plot(range(len(numeric_data)), numeric_data, marker='o', linewidth=2, markersize=4)
                ax.set_xlabel('Index', fontsize=10, fontweight='bold')
                ax.set_ylabel('Value', fontsize=10, fontweight='bold')
                ax.set_title(title, fontsize=12, fontweight='bold', pad=20)
                ax.grid(True, alpha=0.3)
            else:
                self._create_bar_chart(ax, data, title)
        except:
            self._create_bar_chart(ax, data, title)
    
    def _create_histogram(self, ax, data: List[str], title: str):
        try:
            numeric_data = [float(d) for d in data if self._is_numeric(d)]
            
            if numeric_data:
                ax.hist(numeric_data, bins=20, color='steelblue', alpha=0.7, edgecolor='black')
                ax.set_xlabel('Value', fontsize=10, fontweight='bold')
                ax.set_ylabel('Frequency', fontsize=10, fontweight='bold')
                ax.set_title(title, fontsize=12, fontweight='bold', pad=20)
                ax.grid(True, alpha=0.3, axis='y')
            else:
                self._create_bar_chart(ax, data, title)
        except:
            self._create_bar_chart(ax, data, title)
    
    def _create_scatter_chart(self, ax, data: List[str], title: str):
        try:
            numeric_data = [float(d) for d in data if self._is_numeric(d)]
            
            if numeric_data:
                x = range(len(numeric_data))
                y = numeric_data
                ax.scatter(x, y, alpha=0.6, s=50, color='steelblue')
                ax.set_xlabel('Index', fontsize=10, fontweight='bold')
                ax.set_ylabel('Value', fontsize=10, fontweight='bold')
                ax.set_title(title, fontsize=12, fontweight='bold', pad=20)
                ax.grid(True, alpha=0.3)
            else:
                self._create_bar_chart(ax, data, title)
        except:
            self._create_bar_chart(ax, data, title)
    
    def _is_numeric(self, value: str) -> bool:
        try:
            float(value)
            return True
        except:
            return False


chart_generator = ChartGenerator()

