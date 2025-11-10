const API_BASE = '/api';

let currentJobId = null;
let selectedFile = null;
let pollInterval = null;

const uploadArea = document.getElementById('upload-area');
const fileInput = document.getElementById('file-input');
const browseBtn = document.getElementById('browse-btn');
const surveyTopicInput = document.getElementById('survey-topic');
const processBtn = document.getElementById('process-btn');
const downloadBtn = document.getElementById('download-btn');
const newAnalysisBtn = document.getElementById('new-analysis-btn');
const retryBtn = document.getElementById('retry-btn');

const uploadSection = document.getElementById('upload-section');
const processingSection = document.getElementById('processing-section');
const resultsSection = document.getElementById('results-section');
const errorSection = document.getElementById('error-section');

const progressMessage = document.getElementById('progress-message');
const markdownPreview = document.getElementById('markdown-preview');
const errorMessage = document.getElementById('error-message');

function showSection(section) {
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    section.classList.add('active');
}

uploadArea.addEventListener('click', () => fileInput.click());
browseBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    fileInput.click();
});

uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('drag-over');
});

uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('drag-over');
});

uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('drag-over');
    
    const files = e.dataTransfer.files;
    if (files.length > 0 && files[0].name.endsWith('.csv')) {
        handleFileSelect(files[0]);
    } else {
        showError('Please drop a valid CSV file');
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFileSelect(e.target.files[0]);
    }
});

function handleFileSelect(file) {
    selectedFile = file;
    uploadArea.querySelector('h2').textContent = file.name;
    uploadArea.querySelector('p').textContent = `${(file.size / 1024).toFixed(1)} KB`;
    processBtn.disabled = false;
}

processBtn.addEventListener('click', async () => {
    if (!selectedFile) return;
    
    const formData = new FormData();
    formData.append('file', selectedFile);
    
    const surveyTopic = surveyTopicInput.value.trim();
    if (surveyTopic) {
        formData.append('survey_topic', surveyTopic);
    }
    
    try {
        showSection(processingSection);
        updateProgress(0, 'Uploading CSV...', 'Please wait while we upload your file', 'Upload');
        
        const response = await fetch(`${API_BASE}/process-csv`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'Upload failed');
        }
        
        const data = await response.json();
        currentJobId = data.job_id;
        
        console.log('Job created:', currentJobId);
        updateProgress(5, 'Upload complete! Starting analysis...', 'Initializing AI processor', 'Starting');
        
        startPolling();
    } catch (error) {
        console.error('Upload error:', error);
        showError(error.message);
    }
});

function startPolling() {
    pollInterval = setInterval(checkStatus, 2000);
    checkStatus();
}

function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

async function checkStatus() {
    try {
        const response = await fetch(`${API_BASE}/status/${currentJobId}`);
        const data = await response.json();
        
        console.log('Status update:', data);
        
        updateProgress(
            data.progress, 
            data.message,
            data.details,
            data.current_step,
            data.total_questions,
            data.processed_questions
        );
        
        if (data.status === 'completed') {
            stopPolling();
            if (data.markdown_content) {
                displayResults(data.markdown_content);
            } else {
                await loadResults();
            }
        } else if (data.status === 'failed') {
            stopPolling();
            showError(data.error || data.message || 'Processing failed');
        }
    } catch (error) {
        console.error('Status check error:', error);
        stopPolling();
        showError('Failed to check status: ' + error.message);
    }
}

async function displayResults(markdown) {
    markdownPreview.innerHTML = marked.parse(markdown);
    
    await renderMermaidDiagrams();
    
    showSection(resultsSection);
}

async function renderMermaidDiagrams() {
    const mermaidBlocks = markdownPreview.querySelectorAll('code.language-mermaid');
    
    for (let i = 0; i < mermaidBlocks.length; i++) {
        const block = mermaidBlocks[i];
        const code = block.textContent;
        
        const container = document.createElement('div');
        container.className = 'mermaid-container';
        container.style.textAlign = 'center';
        container.style.margin = '2rem 0';
        
        try {
            const { svg } = await mermaid.render(`mermaid-${i}-${Date.now()}`, code);
            container.innerHTML = svg;
            
            block.parentElement.replaceWith(container);
        } catch (error) {
            console.error('Mermaid rendering error:', error);
            container.innerHTML = `<pre style="color: #cc4141; background: #fff5f5; padding: 1rem; border-radius: 0.5rem;">Failed to render diagram: ${error.message}</pre>`;
            block.parentElement.replaceWith(container);
        }
    }
}

function updateProgress(percent, message, details, currentStep, totalQuestions, processedQuestions) {
    progressMessage.textContent = message || 'Processing...';
    
    console.log(`Progress update: ${message}`);
    
    const detailsContainer = document.getElementById('progress-details');
    if (!detailsContainer) {
        const container = document.querySelector('.progress-container');
        const detailsDiv = document.createElement('div');
        detailsDiv.id = 'progress-details';
        detailsDiv.style.marginTop = '1rem';
        detailsDiv.style.fontSize = '0.9rem';
        detailsDiv.style.color = 'var(--text-secondary)';
        container.appendChild(detailsDiv);
    }
    
    const detailsDiv = document.getElementById('progress-details');
    let detailsHtml = '';
    
    if (currentStep) {
        detailsHtml += `<div style="margin-bottom: 0.5rem;"><strong>Step:</strong> ${currentStep}</div>`;
    }
    
    if (totalQuestions && totalQuestions > 0) {
        detailsHtml += `<div style="margin-bottom: 0.5rem;"><strong>Progress:</strong> ${processedQuestions || 0} / ${totalQuestions} questions</div>`;
    }
    
    if (details) {
        detailsHtml += `<div style="font-style: italic;">${details}</div>`;
    }
    
    detailsDiv.innerHTML = detailsHtml;
}

async function loadResults() {
    try {
        const response = await fetch(`${API_BASE}/download/${currentJobId}`);
        
        if (!response.ok) {
            throw new Error('Failed to load results');
        }
        
        const markdown = await response.text();
        
        await displayResults(markdown);
    } catch (error) {
        showError(error.message);
    }
}

downloadBtn.addEventListener('click', () => {
    window.open(`${API_BASE}/download/${currentJobId}`, '_blank');
});

newAnalysisBtn.addEventListener('click', () => {
    selectedFile = null;
    currentJobId = null;
    fileInput.value = '';
    surveyTopicInput.value = '';
    uploadArea.querySelector('h2').textContent = 'Drop your CSV file here';
    uploadArea.querySelector('p').textContent = 'or click to browse';
    processBtn.disabled = true;
    markdownPreview.innerHTML = '';
    showSection(uploadSection);
});

retryBtn.addEventListener('click', () => {
    showSection(uploadSection);
});

function showError(message) {
    errorMessage.textContent = message;
    showSection(errorSection);
}

if (window.location.pathname === '/' || window.location.pathname === '/static/index.html') {
    showSection(uploadSection);
}

