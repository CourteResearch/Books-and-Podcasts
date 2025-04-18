const progressBar = document.getElementById('progressBar');
const progressText = document.getElementById('progress-text');
const statusMessage = document.getElementById('status-message');
const generateButton = document.getElementById('generateButton');
const downloadLinkContainer = document.getElementById('download-link-container');

// --- Socket.IO Connection ---
// Connect to the Socket.IO server running alongside Flask
// Use window.location.origin to connect to the same host/port the page is served from
const socket = io(window.location.origin);

let generationInProgress = false; // Flag to prevent multiple starts

// --- Event Listeners ---
generateButton.addEventListener('click', () => {
    if (!generationInProgress) {
        console.log('Requesting book generation...');
        socket.emit('start_generation', {}); // Send start event to server
        generationInProgress = true;
        generateButton.disabled = true; // Disable button during generation
        statusMessage.textContent = 'Generation started...';
        progressBar.style.width = '0%';
        progressBar.textContent = '0%';
        progressText.textContent = 'Initializing...';
        downloadLinkContainer.innerHTML = ''; // Clear previous download link
    }
});

// --- Socket.IO Event Handlers ---
socket.on('connect', () => {
    console.log('Connected to server via Socket.IO');
    statusMessage.textContent = 'Connected. Ready to generate.';
    generateButton.disabled = false; // Enable button on connect
});

socket.on('disconnect', () => {
    console.log('Disconnected from server');
    statusMessage.textContent = 'Disconnected from server. Please refresh.';
    generateButton.disabled = true;
});

socket.on('connect_error', (err) => {
    console.error('Connection Error:', err);
    statusMessage.textContent = `Connection Error: ${err.message}. Is the server running?`;
    generateButton.disabled = true;
});

socket.on('status_update', (data) => {
    console.log('Status Update:', data.message);
    statusMessage.textContent = data.message; // Display general status messages
});

socket.on('progress_update', (data) => {
    // data contains { completed: X, total: Y }
    const completed = data.completed;
    const total = data.total;
    console.log(`Progress: ${completed}/${total}`);

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
    console.log('Generation Complete:', data.message);
    statusMessage.textContent = 'Generation Complete!';
    progressText.textContent = 'Finished.';
    generationInProgress = false;
    generateButton.disabled = false; // Re-enable button

    // Add download link
    if (data.pdf_filename) {
        const downloadLink = document.createElement('a');
        // Use the /download route created in app.py
        downloadLink.href = `/download/${encodeURIComponent(data.pdf_filename)}`;
        downloadLink.textContent = `Download ${data.pdf_filename}`;
        // downloadLink.download = data.pdf_filename; // Optional: Suggest filename
        downloadLinkContainer.innerHTML = ''; // Clear previous
        downloadLinkContainer.appendChild(downloadLink);
    }
});

socket.on('generation_error', (data) => {
    console.error('Generation Error:', data.message);
    statusMessage.textContent = `Error: ${data.message}`;
    progressText.textContent = 'Failed.';
    progressBar.style.backgroundColor = '#dc3545'; // Indicate error state (red)
    progressBar.style.width = '100%';
    progressBar.textContent = 'Error';
    generationInProgress = false;
    generateButton.disabled = false; // Re-enable button
});

// Initial state setup
generateButton.disabled = true; // Disabled until connected
