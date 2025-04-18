// --- Ebook Agent Elements & Logic ---
const progressBar = document.getElementById('ebook-progressBar'); // Use ebook specific ID
const progressText = document.getElementById('ebook-progress-text'); // Use ebook specific ID
const statusMessage = document.getElementById('ebook-status-message'); // Use ebook specific ID
const generateButton = document.getElementById('ebook-generateButton'); // Use ebook specific ID
const downloadLinkContainer = document.getElementById('ebook-download-link-container'); // Use ebook specific ID

// Connect to the Ebook agent's Socket.IO server
const socket = io(window.location.origin); // Assumes ebook server runs on same origin
let generationInProgress = false;

// --- Event Listeners ---
generateButton.addEventListener('click', () => {
    if (!generationInProgress) {
        console.log('Requesting ebook generation...');
        socket.emit('start_generation', {}); // Send start event to server
        generationInProgress = true;
        generateButton.disabled = true; // Disable button during generation
        statusMessage.textContent = 'Generation started...';
        progressBar.classList.remove('error'); // Ensure error style is removed
        progressBar.style.backgroundColor = '#4CAF50'; // Reset color
        progressBar.style.width = '0%';
        progressBar.textContent = '0%';
        progressText.textContent = 'Initializing...';
        downloadLinkContainer.innerHTML = ''; // Clear previous download link
    }
});

// --- Socket.IO Event Handlers ---
socket.on('connect', () => {
    console.log('Connected to Ebook server via Socket.IO');
    statusMessage.textContent = 'Connected. Ready to generate Ebook.';
    // Only enable button if a generation wasn't already running before disconnect/reconnect
    generateButton.disabled = generationInProgress;
});

socket.on('disconnect', () => {
    console.log('Disconnected from Ebook server');
    statusMessage.textContent = 'Disconnected from Ebook server. Please refresh.';
    generateButton.disabled = true;
});

socket.on('connect_error', (err) => {
    console.error('Ebook Connection Error:', err);
    statusMessage.textContent = `Ebook Server Connection Error: ${err.message}. Is it running?`;
    generateButton.disabled = true;
});

socket.on('status_update', (data) => {
    console.log('Ebook Status Update:', data.message);
    statusMessage.textContent = data.message; // Display general status messages
});

socket.on('progress_update', (data) => {
    // data contains { completed: X, total: Y }
    const completed = data.completed;
    const total = data.total;
    console.log(`Ebook Progress: ${completed}/${total}`);

    if (total > 0) {
        const percentage = Math.round((completed / total) * 100);
        progressBar.style.width = `${percentage}%`;
        progressBar.textContent = `${percentage}%`;
        progressText.textContent = `Chapter ${completed} of ${total} complete.`;
    } else {
        // Handle case where total is 0 (e.g., initial state)
        progressBar.style.width = '0%';
        progressBar.textContent = '0%';
        progressText.textContent = 'Waiting for outline...';
    }
});

socket.on('generation_complete', (data) => {
    console.log('Ebook Generation Complete:', data.message);
    statusMessage.textContent = 'Ebook Generation Complete!';
    progressText.textContent = 'Finished.';
    generationInProgress = false;
    generateButton.disabled = false; // Re-enable button

    // Add download link
    downloadLinkContainer.innerHTML = ''; // Clear previous
    if (data.pdf_filename) {
        const downloadLink = document.createElement('a');
        // Use the /download route created in the ebook app.py
        downloadLink.href = `/download/${encodeURIComponent(data.pdf_filename)}`;
        downloadLink.textContent = `Download ${data.pdf_filename}`;
        downloadLinkContainer.appendChild(downloadLink);
    } else {
         downloadLinkContainer.textContent = 'PDF filename not provided.';
    }
});

socket.on('generation_error', (data) => {
    console.error('Ebook Generation Error:', data.message);
    statusMessage.textContent = `Error: ${data.message}`;
    progressText.textContent = 'Failed.';
    progressBar.classList.add('error'); // Add error class for styling
    progressBar.style.width = '100%';
    progressBar.textContent = 'Error';
    generationInProgress = false;
    generateButton.disabled = false; // Re-enable button
});

// Initial state setup
generateButton.disabled = true; // Disabled until connected
