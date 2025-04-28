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
// New elements for approval
const podcastApprovalContainer = document.getElementById('podcast-approval-container');
const proposedTopicText = document.getElementById('proposed-topic-text');
const podcastApproveButton = document.getElementById('podcast-approveButton');
const podcastRejectButton = document.getElementById('podcast-rejectButton');


// Podcast API now runs on the same server/origin
const PODCAST_API_BASE_URL = window.location.origin; // Both APIs run on the same server now

let podcastGenerationInProgress = false; // True if any part of the process is active (generating topic, awaiting, generating content)
let podcastPollingInterval = null;
let currentProposedTopic = null; // Store the topic received for approval

// --- Event Listeners ---

// Main button now starts TOPIC generation
podcastGenerateButton.addEventListener('click', startTopicGeneration);

// Approval button starts CONTENT generation
podcastApproveButton.addEventListener('click', () => {
    if (currentProposedTopic && podcastGenerationInProgress) {
        console.log(`Approving topic: ${currentProposedTopic}`);
        podcastApprovalContainer.style.display = 'none'; // Hide approval section
        podcastStatusMessage.textContent = `Topic '${currentProposedTopic}' approved. Starting content generation...`;
        podcastProgressText.textContent = 'Requesting content generation...';
        // Disable approval buttons while request is sent
        podcastApproveButton.disabled = true;
        podcastRejectButton.disabled = true;

        // Call the /generate-podcast endpoint with the approved topic
        fetch(`${PODCAST_API_BASE_URL}/generate-podcast`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topic: currentProposedTopic }) // Send approved topic
        })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(err => { throw new Error(err.error || `HTTP error ${response.status}`) });
                }
                return response.json();
            })
            .then(data => {
                console.log('Podcast content generation started:', data.message);
                podcastStatusMessage.textContent = 'Content generation in progress...';
                podcastProgressText.textContent = 'Generating episodes... (Polling)';
                // Restart polling to track content generation
                startPodcastStatusPolling();
            })
            .catch(error => {
                console.error('Error starting podcast content generation:', error);
                // Re-enable buttons on error starting content gen
                podcastApproveButton.disabled = false;
                podcastRejectButton.disabled = false;
                handlePodcastError(`Error starting content generation: ${error.message}`);
            });
    } else {
        console.error("Cannot approve: No current topic or process not active.");
    }
});

// Reject button starts TOPIC generation again
podcastRejectButton.addEventListener('click', () => {
    // Check if we are in a state where rejection makes sense (awaiting approval)
    // We know podcastGenerationInProgress should be true in this state
    if (podcastGenerationInProgress && currentProposedTopic) {
        console.log('Rejecting topic and requesting a new one.');
        podcastApprovalContainer.style.display = 'none'; // Hide approval section
        podcastApproveButton.disabled = true; // Disable buttons immediately
        podcastRejectButton.disabled = true;
        currentProposedTopic = null; // Clear stored topic

        // IMPORTANT: Temporarily set inProgress to false so startTopicGeneration runs
        // It will be set back to true inside startTopicGeneration.
        podcastGenerationInProgress = false;

        // Re-trigger the topic generation flow
        startTopicGeneration();
    } else {
        console.warn("Reject button clicked in unexpected state.");
    }
});


// --- Functions ---

function startTopicGeneration() {
     if (!podcastGenerationInProgress) {
        console.log('Requesting podcast *topic* generation via API...');
        podcastGenerationInProgress = true; // Mark process as active
        podcastGenerateButton.disabled = true; // Disable main button
        podcastApprovalContainer.style.display = 'none'; // Ensure approval is hidden
        podcastStatusMessage.textContent = 'Requesting new topic...';
        podcastProgressBar.classList.remove('error');
        podcastProgressBar.style.backgroundColor = '#4CAF50'; // Reset color
        podcastProgressBar.style.width = '5%'; // Small progress indication
        podcastProgressBar.textContent = 'Starting...';
        podcastProgressText.textContent = 'Finding topic...';
        podcastDownloadLinkContainer.innerHTML = ''; // Clear previous downloads

        // Call the new /generate-podcast-topic endpoint
        fetch(`${PODCAST_API_BASE_URL}/generate-podcast-topic`, { method: 'POST' })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(err => { throw new Error(err.error || `HTTP error ${response.status}`) });
                }
                return response.json();
            })
            .then(data => {
                console.log('Podcast topic generation started:', data.message);
                podcastStatusMessage.textContent = 'Generating topic...';
                podcastProgressText.textContent = 'Waiting for topic... (Polling)';
                // Start polling to wait for the topic or errors
                startPodcastStatusPolling();
            })
            .catch(error => {
                console.error('Error starting podcast topic generation:', error);
                handlePodcastError(`Error starting topic generation: ${error.message}`);
            });
    }
}


function startPodcastStatusPolling() {
    if (podcastPollingInterval) clearInterval(podcastPollingInterval);

    podcastPollingInterval = setInterval(() => {
        fetch(`${PODCAST_API_BASE_URL}/status-podcast`)
            .then(response => {
                if (!response.ok) throw new Error(`HTTP error ${response.status}`);
                return response.json();
            })
            .then(data => {
                console.log('Podcast Status Poll:', data);
                podcastStatusMessage.textContent = data.message || 'Polling status...';
                podcastProgressBar.classList.remove('error'); // Assume not error unless specified

                // Handle different statuses
                switch (data.status) {
                    case 'generating_topic':
                        podcastProgressText.textContent = 'Finding a great topic...';
                        podcastProgressBar.style.width = '25%';
                        podcastProgressBar.textContent = 'Finding Topic';
                        podcastGenerateButton.disabled = true; // Keep disabled
                        podcastApprovalContainer.style.display = 'none'; // Hide approval
                        break;
                    case 'awaiting_approval':
                        podcastProgressText.textContent = 'Topic proposed. Please review.';
                        podcastProgressBar.style.width = '40%'; // Indicate waiting state
                        podcastProgressBar.textContent = 'Approval Needed';
                        currentProposedTopic = data.proposed_topic; // Store the topic
                        proposedTopicText.textContent = currentProposedTopic || 'Error: Topic not found';
                        podcastApprovalContainer.style.display = 'block'; // Show approval section
                        podcastApproveButton.disabled = false; // Enable approval buttons
                        podcastRejectButton.disabled = false;
                        podcastGenerateButton.disabled = true; // Keep main button disabled
                        // Stop polling while waiting for user input
                        if (podcastPollingInterval) clearInterval(podcastPollingInterval);
                        console.log("Status is awaiting_approval, stopping polling.");
                        break;
                    case 'generating_podcast':
                        podcastProgressText.textContent = 'Generating podcast episodes...';
                        podcastProgressBar.style.width = '75%';
                        podcastProgressBar.textContent = 'Generating Content';
                        podcastGenerateButton.disabled = true; // Keep disabled
                        podcastApprovalContainer.style.display = 'none'; // Hide approval
                        break;
                    case 'completed':
                        handlePodcastCompletion(data); // Handle completion (updates UI, enables button)
                        clearInterval(podcastPollingInterval);
                        break;
                    case 'error':
                        handlePodcastError(data.error || data.message || 'Unknown error'); // Handle error (updates UI, enables button)
                        clearInterval(podcastPollingInterval);
                        break;
                    case 'idle':
                        // If we were in progress and suddenly went idle, treat as error/unexpected stop
                        if (podcastGenerationInProgress) {
                            console.warn("Polling found idle status unexpectedly for podcast.");
                            handlePodcastError("Process stopped unexpectedly.");
                        } else {
                            // Otherwise, just ensure UI is reset and stop polling
                            resetPodcastUI();
                        }
                        clearInterval(podcastPollingInterval);
                        break;
                    default:
                        podcastProgressText.textContent = `Unknown status: ${data.status}`;
                        podcastProgressBar.style.width = '50%'; // Generic progress
                        podcastProgressBar.textContent = 'Working...';
                }
            })
            .catch(error => {
                console.error('Error polling podcast status:', error);
                // Don't necessarily stop polling on network error, maybe show temporary message
                 podcastStatusMessage.textContent = `Polling error: ${error.message}. Retrying...`;
                 // handlePodcastError(`Polling failed: ${error.message}`); // Or stop polling on error
            });
    }, 3000); // Poll every 3 seconds
}

function handlePodcastCompletion(data) {
    console.log('Podcast Generation Complete:', data.message);
    podcastStatusMessage.textContent = 'Podcast Series Generation Complete!';
    podcastProgressText.textContent = 'Finished.';
    podcastProgressBar.style.width = '100%';
    podcastProgressBar.textContent = 'Done';
    resetPodcastUI(); // Use helper to reset UI elements

    podcastDownloadLinkContainer.innerHTML = ''; // Clear previous links
    if (data.pdf_filenames && data.pdf_filenames.length > 0) {
        const list = document.createElement('ul');
        // Styles moved to CSS if preferred, kept here for example clarity
        list.style.listStyle = 'none';
        list.style.padding = '0';
        list.style.marginTop = '10px';
        data.pdf_filenames.forEach(filename => {
            const listItem = document.createElement('li');
            const downloadLink = document.createElement('a');
            downloadLink.href = `${PODCAST_API_BASE_URL}/download/${encodeURIComponent(filename)}`;
            downloadLink.textContent = `Download ${filename}`;
            // Optional: Add target="_blank" to open in new tab
            // downloadLink.target = "_blank";
            listItem.appendChild(downloadLink);
            list.appendChild(listItem);
        });
        podcastDownloadLinkContainer.appendChild(list);
    } else {
        podcastDownloadLinkContainer.textContent = 'No PDF files were generated or returned.';
    }
}

function handlePodcastError(errorMessage) {
    console.error('Podcast Generation Error:', errorMessage);
    podcastStatusMessage.textContent = `Error: ${errorMessage}`;
    podcastProgressText.textContent = 'Failed.';
    podcastProgressBar.classList.add('error'); // Add error class for styling
    podcastProgressBar.style.backgroundColor = '#dc3545'; // Explicitly set error color
    podcastProgressBar.style.width = '100%';
    podcastProgressBar.textContent = 'Error';
    resetPodcastUI(); // Use helper to reset UI elements
    if (podcastPollingInterval) clearInterval(podcastPollingInterval); // Ensure polling stops
}

// Helper function to reset podcast UI elements to idle state
function resetPodcastUI() {
    podcastGenerationInProgress = false;
    podcastGenerateButton.disabled = false; // Re-enable main button
    podcastApprovalContainer.style.display = 'none'; // Hide approval section
    podcastApproveButton.disabled = true; // Disable approval buttons
    podcastRejectButton.disabled = true;
    currentProposedTopic = null; // Clear stored topic
    // Optionally reset progress bar appearance fully
    // podcastProgressBar.style.width = '0%';
    // podcastProgressBar.textContent = '';
    // podcastProgressBar.classList.remove('error');
    // podcastProgressBar.style.backgroundColor = '#4CAF50'; // Reset color
}


// --- Initial State ---
resetPodcastUI(); // Initialize UI state on load
// Initial status messages can be set here or in HTML
podcastStatusMessage.textContent = 'Ready to generate podcast topic.';
podcastProgressText.textContent = 'Waiting to start...';
