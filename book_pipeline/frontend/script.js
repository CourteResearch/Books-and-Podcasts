// --- Common Elements ---
// (Assuming IDs are unique as set in index.html)

// --- Ebook Agent Elements & Logic ---
const ebookProgressBar = document.getElementById('ebook-progressBar');
const ebookProgressText = document.getElementById('ebook-progress-text');
const ebookStatusMessage = document.getElementById('ebook-status-message');
const ebookGenerateButton = document.getElementById('ebook-generateButton');
const ebookDownloadLinkContainer = document.getElementById('ebook-download-link-container');

// Connect to the Ebook agent's Socket.IO server (assuming it runs on the same origin or specify URL)
// NOTE: This assumes the ebook agent (book_pipeline/app.py) is running!
const ebookSocket = io(window.location.origin); // Adjust if ebook server is elsewhere
let ebookGenerationInProgress = false;

ebookGenerateButton.addEventListener('click', () => {
    if (!ebookGenerationInProgress) {
        console.log('Requesting ebook generation...');
        ebookSocket.emit('start_generation', {});
        ebookGenerationInProgress = true;
        ebookGenerateButton.disabled = true;
        ebookStatusMessage.textContent = 'Generation started...';
        ebookProgressBar.classList.remove('error');
        ebookProgressBar.style.backgroundColor = '#4CAF50'; // Reset color
        ebookProgressBar.style.width = '0%';
        ebookProgressBar.textContent = '0%';
        ebookProgressText.textContent = 'Initializing...';
        ebookDownloadLinkContainer.innerHTML = '';
    }
});

ebookSocket.on('connect', () => {
    console.log('Connected to Ebook server');
    ebookStatusMessage.textContent = 'Connected. Ready to generate Ebook.';
    ebookGenerateButton.disabled = ebookGenerationInProgress; // Only enable if not already running
});

ebookSocket.on('disconnect', () => {
    console.log('Disconnected from Ebook server');
    ebookStatusMessage.textContent = 'Disconnected from Ebook server. Please refresh.';
    ebookGenerateButton.disabled = true;
});

ebookSocket.on('connect_error', (err) => {
    console.error('Ebook Connection Error:', err);
    ebookStatusMessage.textContent = `Ebook Server Connection Error. Is it running?`;
    ebookGenerateButton.disabled = true;
});

ebookSocket.on('status_update', (data) => {
    console.log('Ebook Status Update:', data.message);
    ebookStatusMessage.textContent = data.message;
});

ebookSocket.on('progress_update', (data) => {
    const completed = data.completed;
    const total = data.total;
    console.log(`Ebook Progress: ${completed}/${total}`);
    if (total > 0) {
        const percentage = Math.round((completed / total) * 100);
        ebookProgressBar.style.width = `${percentage}%`;
        ebookProgressBar.textContent = `${percentage}%`;
        ebookProgressText.textContent = `Chapter ${completed} of ${total} complete.`;
    } else {
        ebookProgressBar.style.width = '0%';
        ebookProgressBar.textContent = '0%';
        ebookProgressText.textContent = 'Waiting for outline...';
    }
});

ebookSocket.on('generation_complete', (data) => {
    console.log('Ebook Generation Complete:', data.message);
    ebookStatusMessage.textContent = 'Ebook Generation Complete!';
    ebookProgressText.textContent = 'Finished.';
    ebookGenerationInProgress = false;
    ebookGenerateButton.disabled = false;
    if (data.pdf_filename) {
        const downloadLink = document.createElement('a');
        // Assuming ebook app.py serves download from its root
        downloadLink.href = `/download/${encodeURIComponent(data.pdf_filename)}`;
        downloadLink.textContent = `Download ${data.pdf_filename}`;
        ebookDownloadLinkContainer.innerHTML = '';
        ebookDownloadLinkContainer.appendChild(downloadLink);
    }
});

ebookSocket.on('generation_error', (data) => {
    console.error('Ebook Generation Error:', data.message);
    ebookStatusMessage.textContent = `Error: ${data.message}`;
    ebookProgressText.textContent = 'Failed.';
    ebookProgressBar.classList.add('error'); // Add error class
    ebookProgressBar.style.width = '100%';
    ebookProgressBar.textContent = 'Error';
    ebookGenerationInProgress = false;
    ebookGenerateButton.disabled = false;
});

// --- Podcast Agent Elements & Logic ---
const podcastProgressBar = document.getElementById('podcast-progressBar');
const podcastProgressText = document.getElementById('podcast-progress-text');
const podcastStatusMessage = document.getElementById('podcast-status-message');
const podcastGenerateButton = document.getElementById('podcast-generateButton');
const podcastDownloadLinkContainer = document.getElementById('podcast-download-link-container');

// URL for the Podcast API (running separately, likely on port 5001)
// IMPORTANT: Adjust this URL if the podcast API runs elsewhere or on a different port
const PODCAST_API_BASE_URL = 'https://podcasts-api-93x8.onrender.com';

let podcastGenerationInProgress = false;
let podcastEventSource = null; // To hold the EventSource connection

podcastGenerateButton.addEventListener('click', () => {
    if (!podcastGenerationInProgress) {
        console.log('Requesting podcast generation via API...');
        podcastGenerationInProgress = true;
        podcastGenerateButton.disabled = true;
        podcastStatusMessage.textContent = 'Sending request to Podcast API...';
        podcastProgressBar.classList.remove('error');
        podcastProgressBar.style.backgroundColor = '#4CAF50'; // Reset color
        podcastProgressBar.style.width = '0%';
        podcastProgressBar.textContent = '0%';
        podcastProgressText.textContent = 'Initializing...';
        podcastDownloadLinkContainer.innerHTML = ''; // Clear previous links

        // Close existing EventSource if any
        if (podcastEventSource) {
            podcastEventSource.close();
        }

        // 1. Call the /generate endpoint to start
        fetch(`${PODCAST_API_BASE_URL}/generate`, { method: 'POST' })
            .then(response => {
                if (!response.ok) {
                    // Handle immediate errors like "already running"
                    return response.json().then(err => { throw new Error(err.error || `HTTP error ${response.status}`) });
                }
                return response.json();
            })
            .then(data => {
                console.log('Podcast generation started:', data.message);
                podcastStatusMessage.textContent = 'Generation started. Connecting to status stream...';
                // 2. Connect to the SSE stream
                connectToPodcastStream();
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

function connectToPodcastStream() {
    console.log(`Connecting to SSE stream: ${PODCAST_API_BASE_URL}/stream`);
    podcastEventSource = new EventSource(`${PODCAST_API_BASE_URL}/stream`);

    podcastEventSource.onopen = () => {
        console.log('SSE Connection opened.');
        podcastStatusMessage.textContent = 'Connected to status stream. Waiting for updates...';
    };

    podcastEventSource.onerror = (error) => {
        console.error('SSE Error:', error);
        podcastStatusMessage.textContent = 'Error connecting to status stream. Retrying?';
        // EventSource automatically tries to reconnect on error.
        // We might want to close it manually after too many errors.
        // podcastEventSource.close(); // Example: close on error
        // podcastGenerationInProgress = false;
        // podcastGenerateButton.disabled = false;
    };

    podcastEventSource.onmessage = (event) => {
        try {
            const messageData = JSON.parse(event.data);
            console.log('SSE Message Received:', messageData);

            switch (messageData.type) {
                case 'status':
                    podcastStatusMessage.textContent = messageData.data.message;
                    break;
                case 'progress':
                    updatePodcastProgressBar(messageData.data.completed, messageData.data.total);
                    break;
                case 'error':
                    handlePodcastError(messageData.data.message);
                    podcastEventSource.close(); // Close stream on definitive error
                    break;
                case 'finished':
                    handlePodcastCompletion(messageData.data);
                    podcastEventSource.close(); // Close stream on completion
                    break;
                default:
                    console.warn('Unknown SSE message type:', messageData.type);
            }
        } catch (e) {
            console.error('Error parsing SSE message:', e, 'Data:', event.data);
        }
    };
}

function updatePodcastProgressBar(completed, total) {
    if (total > 0) {
        const percentage = Math.round((completed / total) * 100);
        podcastProgressBar.style.width = `${percentage}%`;
        podcastProgressBar.textContent = `${percentage}%`;
        podcastProgressText.textContent = `Episode ${completed} of ${total} generated.`;
    } else {
        podcastProgressBar.style.width = '0%';
        podcastProgressBar.textContent = '0%';
        podcastProgressText.textContent = 'Waiting for outline...';
    }
}

function handlePodcastCompletion(data) {
    console.log('Podcast Generation Complete:', data.message);
    podcastStatusMessage.textContent = 'Podcast Series Generation Complete!';
    podcastProgressText.textContent = 'Finished.';
    podcastGenerationInProgress = false;
    podcastGenerateButton.disabled = false;

    podcastDownloadLinkContainer.innerHTML = ''; // Clear previous
    if (data.pdf_filenames && data.pdf_filenames.length > 0) {
        const list = document.createElement('ul');
        list.style.listStyle = 'none';
        list.style.padding = '0';
        list.style.marginTop = '10px';
        data.pdf_filenames.forEach(filename => {
            const listItem = document.createElement('li');
            const downloadLink = document.createElement('a');
            // Use the /download route from the podcast API
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
}

// --- Initial State ---
ebookGenerateButton.disabled = true; // Disabled until connected to ebook server
// Podcast button is enabled by default, disabled on click
