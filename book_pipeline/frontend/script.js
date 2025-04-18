// --- Ebook Agent Elements & Logic (Using API Polling) ---
const ebookProgressBar = document.getElementById('ebook-progressBar');
const ebookProgressText = document.getElementById('ebook-progress-text'); // Still used for final status
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
        ebookProgressBar.style.width = '0%'; // Reset progress bar visually
        ebookProgressBar.textContent = 'Starting...';
        ebookProgressText.textContent = 'Initializing...';
        ebookDownloadLinkContainer.innerHTML = '';

        // Call the /generate endpoint
        fetch(`${EBOOK_API_BASE_URL}/generate`, { method: 'POST' })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(err => { throw new Error(err.error || `HTTP error ${response.status}`) });
                }
                return response.json();
            })
            .then(data => {
                console.log('Ebook generation started:', data.message);
                ebookStatusMessage.textContent = 'Generation in progress...';
                ebookProgressText.textContent = 'Running... (Status polling)'; // Indicate polling
                // Start polling the status endpoint
                startEbookStatusPolling();
            })
            .catch(error => {
                console.error('Error starting ebook generation:', error);
                ebookStatusMessage.textContent = `Error starting: ${error.message}`;
                ebookGenerationInProgress = false;
                ebookGenerateButton.disabled = false;
                ebookProgressBar.classList.add('error');
                ebookProgressBar.style.width = '100%';
                ebookProgressBar.textContent = 'Error';
            });
    }
});

function startEbookStatusPolling() {
    // Clear any existing interval
    if (ebookPollingInterval) {
        clearInterval(ebookPollingInterval);
    }

    ebookPollingInterval = setInterval(() => {
        fetch(`${EBOOK_API_BASE_URL}/status`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('Ebook Status Poll:', data);
                ebookStatusMessage.textContent = data.message || 'Polling status...'; // Update status message

                // Update UI based on status
                if (data.status === 'running') {
                    // Keep polling, maybe update progress text if backend provided more detail
                    ebookProgressText.textContent = 'Running... (Status polling)';
                    ebookProgressBar.style.width = '50%'; // Indicate running visually (no percentage)
                    ebookProgressBar.textContent = 'Running';
                } else if (data.status === 'completed') {
                    handleEbookCompletion(data);
                    clearInterval(ebookPollingInterval); // Stop polling
                } else if (data.status === 'error') {
                    handleEbookError(data.error || data.message || 'Unknown error');
                    clearInterval(ebookPollingInterval); // Stop polling
                } else if (data.status === 'idle') {
                     // Should not happen if we started generation, but handle defensively
                     console.warn("Polling found idle status unexpectedly.");
                     ebookStatusMessage.textContent = "Process finished unexpectedly (idle).";
                     ebookGenerationInProgress = false;
                     ebookGenerateButton.disabled = false;
                     clearInterval(ebookPollingInterval);
                }
            })
            .catch(error => {
                console.error('Error polling ebook status:', error);
                ebookStatusMessage.textContent = `Error polling status: ${error.message}`;
                // Consider stopping polling after too many errors
                // clearInterval(ebookPollingInterval);
                // ebookGenerationInProgress = false;
                // ebookGenerateButton.disabled = false;
            });
    }, 3000); // Poll every 3 seconds
}

function handleEbookCompletion(data) {
    console.log('Ebook Generation Complete:', data.message);
    ebookStatusMessage.textContent = 'Ebook Generation Complete!';
    ebookProgressText.textContent = 'Finished.';
    ebookProgressBar.style.width = '100%';
    ebookProgressBar.textContent = 'Done';
    ebookGenerationInProgress = false;
    ebookGenerateButton.disabled = false;

    ebookDownloadLinkContainer.innerHTML = ''; // Clear previous
    if (data.pdf_filename) {
        const downloadLink = document.createElement('a');
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
}


// --- Podcast Agent Elements & Logic (Using API Polling) ---
const podcastProgressBar = document.getElementById('podcast-progressBar');
const podcastProgressText = document.getElementById('podcast-progress-text'); // Still used for final status
const podcastStatusMessage = document.getElementById('podcast-status-message');
const podcastGenerateButton = document.getElementById('podcast-generateButton');
const podcastDownloadLinkContainer = document.getElementById('podcast-download-link-container');

// URL for the Podcast API - Use the deployed Render URL
const PODCAST_API_BASE_URL = 'https://podcasts-api-93x8.onrender.com';

let podcastGenerationInProgress = false;
let podcastPollingInterval = null; // To hold the polling interval

podcastGenerateButton.addEventListener('click', () => {
    if (!podcastGenerationInProgress) {
        console.log('Requesting podcast generation via API...');
        podcastGenerationInProgress = true;
        podcastGenerateButton.disabled = true;
        podcastStatusMessage.textContent = 'Sending request to Podcast API...';
        podcastProgressBar.classList.remove('error');
        podcastProgressBar.style.backgroundColor = '#4CAF50';
        podcastProgressBar.style.width = '0%';
        podcastProgressBar.textContent = 'Starting...';
        podcastProgressText.textContent = 'Initializing...';
        podcastDownloadLinkContainer.innerHTML = '';

        // Call the /generate endpoint
        fetch(`${PODCAST_API_BASE_URL}/generate`, { method: 'POST' })
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
                // Start polling the status endpoint
                startPodcastStatusPolling();
            })
            .catch(error => {
                console.error('Error starting podcast generation:', error);
                podcastStatusMessage.textContent = `Error starting: ${error.message}`;
                podcastGenerationInProgress = false;
                podcastGenerateButton.disabled = false;
                podcastProgressBar.classList.add('error');
                podcastProgressBar.style.width = '100%';
                podcastProgressBar.textContent = 'Error';
            });
    }
});

function startPodcastStatusPolling() {
    // Clear any existing interval
    if (podcastPollingInterval) {
        clearInterval(podcastPollingInterval);
    }

    podcastPollingInterval = setInterval(() => {
        fetch(`${PODCAST_API_BASE_URL}/status`)
            .then(response => {
                if (!response.ok) {
                    // Handle potential network errors or server issues during polling
                    throw new Error(`HTTP error ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('Podcast Status Poll:', data);
                podcastStatusMessage.textContent = data.message || 'Polling status...';

                // Update UI based on status
                if (data.status === 'running') {
                    podcastProgressText.textContent = 'Running... (Status polling)';
                    podcastProgressBar.style.width = '50%'; // Indicate running
                    podcastProgressBar.textContent = 'Running';
                } else if (data.status === 'completed') {
                    handlePodcastCompletion(data); // Use the existing completion handler
                    clearInterval(podcastPollingInterval); // Stop polling
                } else if (data.status === 'error') {
                    handlePodcastError(data.error || data.message || 'Unknown error'); // Use existing error handler
                    clearInterval(podcastPollingInterval); // Stop polling
                } else if (data.status === 'idle') {
                     console.warn("Polling found idle status unexpectedly.");
                     podcastStatusMessage.textContent = "Process finished unexpectedly (idle).";
                     podcastGenerationInProgress = false;
                     podcastGenerateButton.disabled = false;
                     clearInterval(podcastPollingInterval);
                }
            })
            .catch(error => {
                console.error('Error polling podcast status:', error);
                podcastStatusMessage.textContent = `Error polling status: ${error.message}`;
                // Optionally stop polling after repeated errors
                // clearInterval(podcastPollingInterval);
                // podcastGenerationInProgress = false;
                // podcastGenerateButton.disabled = false;
            });
    }, 3000); // Poll every 3 seconds
}

// Removed connectToPodcastStream function

// Removed updatePodcastProgressBar function (no real-time progress with polling)

function handlePodcastCompletion(data) { // Re-using this function name
    console.log('Podcast Generation Complete:', data.message);
    podcastStatusMessage.textContent = 'Podcast Series Generation Complete!';
    podcastProgressText.textContent = 'Finished.';
    podcastProgressBar.style.width = '100%'; // Show 100% on completion
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

function handlePodcastError(errorMessage) { // Re-using this function name
    console.error('Podcast Generation Error:', errorMessage);
    podcastStatusMessage.textContent = `Error: ${errorMessage}`;
    podcastProgressText.textContent = 'Failed.';
    podcastProgressBar.classList.add('error');
    podcastProgressBar.style.width = '100%';
    podcastProgressBar.textContent = 'Error';
    podcastGenerationInProgress = false;
    podcastGenerateButton.disabled = false;
}

// --- Initial State ---
// Ebook button is enabled by default, disabled on click
// Podcast button is enabled by default, disabled on click
