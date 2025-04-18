// --- Ebook Agent Elements & Logic (Using API Polling) ---
const ebookProgressBar = document.getElementById('ebook-progressBar');
const ebookProgressText = document.getElementById('ebook-progress-text');
const ebookStatusMessage = document.getElementById('ebook-status-message');
const ebookGenerateButton = document.getElementById('ebook-generateButton');
const ebookDownloadLinkContainer = document.getElementById('ebook-download-link-container');

let ebookGenerationInProgress = false;
let ebookPollingInterval = null;
const EBOOK_API_BASE_URL = window.location.origin; // Ebook API runs on same origin as frontend

ebookGenerateButton.addEventListener('click', () => {
    if (!ebookGenerationInProgress) {
        console.log('Requesting ebook generation via API...');
        ebookGenerationInProgress = true;
        ebookGenerateButton.disabled = true;
        ebookStatusMessage.textContent = 'Sending generation request...';
        ebookProgressBar.classList.remove('error');
        ebookProgressBar.style.backgroundColor = '#4CAF50';
        ebookProgressBar.style.width = '0%';
        ebookProgressBar.textContent = 'Starting...';
        ebookProgressText.textContent = 'Initializing...';
        ebookDownloadLinkContainer.innerHTML = '';

        // Call the specific /generate-ebook endpoint
        fetch(`${EBOOK_API_BASE_URL}/generate-ebook`, { method: 'POST' })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(err => { throw new Error(err.error || `HTTP error ${response.status}`) });
                }
                return response.json();
            })
            .then(data => {
                console.log('Ebook generation started:', data.message);
                ebookStatusMessage.textContent = 'Generation in progress...';
                ebookProgressText.textContent = 'Running... (Status polling)';
                startEbookStatusPolling(); // Start polling the specific ebook status endpoint
            })
            .catch(error => {
                console.error('Error starting ebook generation:', error);
                handleEbookError(`Error starting: ${error.message}`); // Use handler
            });
    }
});

function startEbookStatusPolling() {
    if (ebookPollingInterval) clearInterval(ebookPollingInterval);

    ebookPollingInterval = setInterval(() => {
        // Poll the specific /status-ebook endpoint
        fetch(`${EBOOK_API_BASE_URL}/status-ebook`)
            .then(response => {
                if (!response.ok) throw new Error(`HTTP error ${response.status}`);
                return response.json();
            })
            .then(data => {
                console.log('Ebook Status Poll:', data);
                ebookStatusMessage.textContent = data.message || 'Polling status...';

                if (data.status === 'running') {
                    ebookProgressText.textContent = 'Running... (Status polling)';
                    ebookProgressBar.style.width = '50%';
                    ebookProgressBar.textContent = 'Running';
                } else if (data.status === 'completed') {
                    handleEbookCompletion(data);
                    clearInterval(ebookPollingInterval);
                } else if (data.status === 'error') {
                    handleEbookError(data.error || data.message || 'Unknown error');
                    clearInterval(ebookPollingInterval);
                } else if (data.status === 'idle' && ebookGenerationInProgress) { // Check if we were expecting it to run
                     console.warn("Polling found idle status unexpectedly for ebook.");
                     handleEbookError("Process finished unexpectedly (idle).");
                     clearInterval(ebookPollingInterval);
                } else if (data.status === 'idle' && !ebookGenerationInProgress) {
                     // If it's idle and we weren't running, just stop polling
                     clearInterval(ebookPollingInterval);
                }
            })
            .catch(error => {
                console.error('Error polling ebook status:', error);
                ebookStatusMessage.textContent = `Error polling status: ${error.message}`;
                // Optionally stop polling after too many errors
            });
    }, 3000);
}

function handleEbookCompletion(data) {
    console.log('Ebook Generation Complete:', data.message);
    ebookStatusMessage.textContent = 'Ebook Generation Complete!';
    ebookProgressText.textContent = 'Finished.';
    ebookProgressBar.style.width = '100%';
    ebookProgressBar.textContent = 'Done';
    ebookGenerationInProgress = false;
    ebookGenerateButton.disabled = false;

    ebookDownloadLinkContainer.innerHTML = '';
    if (data.pdf_filename) {
        const downloadLink = document.createElement('a');
        // Use the shared download endpoint
        downloadLink.href = `${EBOOK_API_BASE_URL}/download/${encodeURIComponent(data.pdf_filename)}`;
        downloadLink.textContent = `Download ${data.pdf_filename}`;
        ebookDownloadLinkContainer.appendChild(downloadLink);
    } else {
         ebookDownloadLinkContainer.textContent = 'PDF filename not provided.';
    }
}

function handleEbookError(errorMessage) {
    console.error('Ebook Generation Error:', errorMessage);
    ebookStatusMessage.textContent = `Error: ${errorMessage}`;
    ebookProgressText.textContent = 'Failed.';
    ebookProgressBar.classList.add('error');
    ebookProgressBar.style.width = '100%';
    ebookProgressBar.textContent = 'Error';
    ebookGenerationInProgress = false;
    ebookGenerateButton.disabled = false;
    if (ebookPollingInterval) clearInterval(ebookPollingInterval); // Stop polling on error
}


// --- Podcast Agent Elements & Logic (Using API Polling) ---
const podcastProgressBar = document.getElementById('podcast-progressBar');
const podcastProgressText = document.getElementById('podcast-progress-text');
const podcastStatusMessage = document.getElementById('podcast-status-message');
const podcastGenerateButton = document.getElementById('podcast-generateButton');
const podcastDownloadLinkContainer = document.getElementById('podcast-download-link-container');

// Podcast API now runs on the same server/origin
const PODCAST_API_BASE_URL = window.location.origin; // Both APIs run on the same server now

let podcastGenerationInProgress = false;
let podcastPollingInterval = null;

podcastGenerateButton.addEventListener('click', () => {
    if (!podcastGenerationInProgress) {
        console.log('Requesting podcast generation via API...');
        podcastGenerationInProgress = true;
        podcastGenerateButton.disabled = true;
        podcastStatusMessage.textContent = 'Sending generation request...';
        podcastProgressBar.classList.remove('error');
        podcastProgressBar.style.backgroundColor = '#4CAF50';
        podcastProgressBar.style.width = '0%';
        podcastProgressBar.textContent = 'Starting...';
        podcastProgressText.textContent = 'Initializing...';
        podcastDownloadLinkContainer.innerHTML = '';

        // Call the specific /generate-podcast endpoint
        fetch(`${PODCAST_API_BASE_URL}/generate-podcast`, { method: 'POST' })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(err => { throw new Error(err.error || `HTTP error ${response.status}`) });
                }
                return response.json();
            })
            .then(data => {
                console.log('Podcast generation started:', data.message);
                podcastStatusMessage.textContent = 'Generation in progress...';
                podcastProgressText.textContent = 'Running... (Status polling)';
                // Start polling the specific podcast status endpoint
                startPodcastStatusPolling();
            })
            .catch(error => {
                console.error('Error starting podcast generation:', error);
                handlePodcastError(`Error starting: ${error.message}`); // Use handler
            });
    }
});

function startPodcastStatusPolling() {
    if (podcastPollingInterval) clearInterval(podcastPollingInterval);

    podcastPollingInterval = setInterval(() => {
        // Poll the specific /status-podcast endpoint
        fetch(`${PODCAST_API_BASE_URL}/status-podcast`)
            .then(response => {
                if (!response.ok) throw new Error(`HTTP error ${response.status}`);
                return response.json();
            })
            .then(data => {
                console.log('Podcast Status Poll:', data);
                podcastStatusMessage.textContent = data.message || 'Polling status...';

                if (data.status === 'running') {
                    podcastProgressText.textContent = 'Running... (Status polling)';
                    podcastProgressBar.style.width = '50%';
                    podcastProgressBar.textContent = 'Running';
                } else if (data.status === 'completed') {
                    handlePodcastCompletion(data);
                    clearInterval(podcastPollingInterval);
                } else if (data.status === 'error') {
                    handlePodcastError(data.error || data.message || 'Unknown error');
                    clearInterval(podcastPollingInterval);
                } else if (data.status === 'idle' && podcastGenerationInProgress) {
                     console.warn("Polling found idle status unexpectedly for podcast.");
                     handlePodcastError("Process finished unexpectedly (idle).");
                     clearInterval(podcastPollingInterval);
                } else if (data.status === 'idle' && !podcastGenerationInProgress) {
                     clearInterval(podcastPollingInterval);
                }
            })
            .catch(error => {
                console.error('Error polling podcast status:', error);
                podcastStatusMessage.textContent = `Error polling status: ${error.message}`;
                // Optionally stop polling
            });
    }, 3000); // Poll every 3 seconds
}

function handlePodcastCompletion(data) {
    console.log('Podcast Generation Complete:', data.message);
    podcastStatusMessage.textContent = 'Podcast Series Generation Complete!';
    podcastProgressText.textContent = 'Finished.';
    podcastProgressBar.style.width = '100%';
    podcastProgressBar.textContent = 'Done';
    podcastGenerationInProgress = false;
    podcastGenerateButton.disabled = false;

    podcastDownloadLinkContainer.innerHTML = '';
    if (data.pdf_filenames && data.pdf_filenames.length > 0) {
        const list = document.createElement('ul');
        list.style.listStyle = 'none';
        list.style.padding = '0';
        list.style.marginTop = '10px';
        data.pdf_filenames.forEach(filename => {
            const listItem = document.createElement('li');
            const downloadLink = document.createElement('a');
            // Use the shared download endpoint
            downloadLink.href = `${PODCAST_API_BASE_URL}/download/${encodeURIComponent(filename)}`;
            downloadLink.textContent = `Download ${filename}`;
            listItem.appendChild(downloadLink);
            list.appendChild(listItem);
        });
        podcastDownloadLinkContainer.appendChild(list);
    } else {
        podcastDownloadLinkContainer.textContent = 'No PDF files were generated.';
    }
}

function handlePodcastError(errorMessage) {
    console.error('Podcast Generation Error:', errorMessage);
    podcastStatusMessage.textContent = `Error: ${errorMessage}`;
    podcastProgressText.textContent = 'Failed.';
    podcastProgressBar.classList.add('error');
    podcastProgressBar.style.width = '100%';
    podcastProgressBar.textContent = 'Error';
    podcastGenerationInProgress = false;
    podcastGenerateButton.disabled = false;
    if (podcastPollingInterval) clearInterval(podcastPollingInterval); // Stop polling on error
}

// --- Initial State ---
// Buttons are enabled by default, disabled on click
