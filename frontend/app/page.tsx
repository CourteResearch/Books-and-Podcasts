'use client'; // Required for useState and useEffect

import React, { useState, useEffect, useRef } from 'react';
// NOTE: Assuming generateVideo is exported from the backend module.
// If the backend function isn't directly callable from frontend,
// you'll need an API endpoint instead. Corrected path assuming video_generator is outside frontend.
// import { generateVideo } from '../../video_generator/video_generator';

// Define interfaces for the expected state shapes from the backend
interface EbookState {
    is_generating: boolean;
    status: string; // idle, generating_concept, awaiting_approval, running, completed, error
    message: string;
    proposed_title?: string | null;
    proposed_premise?: string | null;
    current_genre?: string | null; // Added to track genre
    pdf_filename?: string | null;
    error?: string | null;
}

interface PodcastState {
    is_generating: boolean;
    status: string; // idle, generating_topic, awaiting_approval, generating_podcast, completed, error
    message: string;
    proposed_topic?: string | null;
    pdf_filenames?: string[];
    error?: string | null;
}

interface VideoState {
    is_generating: boolean;
    status: string; // idle, generating_topic, awaiting_approval, generating_video, completed, error
    message: string;
    proposed_topic?: string | null; 
    video_filenames?: string[]; 
    error?: string | null;
    current_episode?: string | null; // To track which episode is being processed
}

interface PodcastEpisodeFile {
    filename: string;
    has_prompts: boolean;
    // has_video: boolean; // Can be added later
}

const API_BASE_URL = 'http://localhost:5000'; 

export default function Home() {
    // --- State Variables ---
    const [ebookState, setEbookState] = useState<EbookState>({
        is_generating: false,
        status: 'idle',
        message: 'Ready for Ebook generation.',
        proposed_title: null,
        proposed_premise: null,
        current_genre: null,
        pdf_filename: null,
        error: null,
    });

    const [podcastState, setPodcastState] = useState<PodcastState>({
        is_generating: false,
        status: 'idle',
        message: 'Ready for Podcast generation.',
        proposed_topic: null,
        pdf_filenames: [],
        error: null,
    });

    const [videoState, setVideoState] = useState<VideoState>({
        is_generating: false,
        status: 'idle',
        message: 'Ready for Video generation.',
        proposed_topic: null, 
        video_filenames: [], 
        error: null,
        current_episode: null,
    });

    const [podcastTopicInput, setPodcastTopicInput] = useState('');
    // const [videoTopicInput, setVideoTopicInput] = useState(''); // No longer needed as we list episodes

    const [podcastEpisodes, setPodcastEpisodes] = useState<PodcastEpisodeFile[]>([]);

    // --- Helper Functions ---
    const pollStatus = async (
        url: string,
        setState: React.Dispatch<React.SetStateAction<any>>, // eslint-disable-line @typescript-eslint/no-explicit-any
        intervalIdRef: React.MutableRefObject<NodeJS.Timeout | null>
    ) => {
        try {
            const response = await fetch(url);
            if (!response.ok) {
                console.error(`Polling failed: ${response.statusText}`);
                // Optionally stop polling on certain errors
                return;
            }
            const data = await response.json();
            setState(data);

            // Stop polling if generation is complete or errored
            if (data.status === 'completed' || data.status === 'error') {
                if (intervalIdRef.current) {
                    clearInterval(intervalIdRef.current);
                    intervalIdRef.current = null;
                    console.log(`Polling stopped for ${url}`);
                }
            }
        } catch (error) {
            console.error(`Error during polling ${url}:`, error);
            // Optionally stop polling on network errors
            if (intervalIdRef.current) {
                clearInterval(intervalIdRef.current);
                intervalIdRef.current = null;
            }
        }
    };

    // Refs to store interval IDs
    const ebookIntervalId = useRef<NodeJS.Timeout | null>(null);
    const podcastIntervalId = useRef<NodeJS.Timeout | null>(null);
    const videoIntervalId = useRef<NodeJS.Timeout | null>(null); 

    // --- Effect for Polling & Initial Data Load ---
    useEffect(() => {
        fetchPodcastEpisodes(); // Fetch episodes on component mount

        // Cleanup function to clear intervals when component unmounts
        return () => {
            if (ebookIntervalId.current) clearInterval(ebookIntervalId.current);
            if (podcastIntervalId.current) clearInterval(podcastIntervalId.current);
            if (videoIntervalId.current) clearInterval(videoIntervalId.current); 
        };
    }, []); 

    const fetchPodcastEpisodes = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/list-podcast-episodes`);
            if (!response.ok) {
                console.error('Failed to fetch podcast episodes list');
                setPodcastEpisodes([]); // Set to empty or handle error state
                return;
            }
            const data = await response.json();
            setPodcastEpisodes(data.episodes || []);
        } catch (error) {
            console.error('Error fetching podcast episodes:', error);
            setPodcastEpisodes([]);
        }
    };

    // Function to start polling for a specific process
    const startPolling = (
        statusUrl: string,
        setState: React.Dispatch<React.SetStateAction<any>>, // eslint-disable-line @typescript-eslint/no-explicit-any
        intervalIdRef: React.MutableRefObject<NodeJS.Timeout | null>
    ) => {
        // Clear existing interval if any
        if (intervalIdRef.current) {
            clearInterval(intervalIdRef.current);
        }
        // Poll immediately first time
        pollStatus(statusUrl, setState, intervalIdRef);
        // Start interval
        intervalIdRef.current = setInterval(() => {
            pollStatus(statusUrl, setState, intervalIdRef);
        }, 3000); // Poll every 3 seconds
        console.log(`Polling started for ${statusUrl}`);
    };

    // --- API Call Handlers ---

    // Ebook Handlers
    const handleGenerateEbookConcept = async (genre: string) => {
        try {
            const response = await fetch(`${API_BASE_URL}/generate-ebook-concept`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ genre }), // Send genre in the request body
            });
            const data = await response.json();
            if (!response.ok) {
                setEbookState(prev => ({ ...prev, status: 'error', message: data.error || `Error: ${response.statusText}`, error: data.error || `Failed to start ${genre} concept generation.`, current_genre: genre }));
                return;
            }
            // Message from backend should ideally include the genre now
            setEbookState(prev => ({ ...prev, status: 'generating_concept', message: data.message || `Concept generation for ${genre} started...`, current_genre: genre }));
            startPolling(`${API_BASE_URL}/status-ebook`, setEbookState, ebookIntervalId);
        } catch (error) {
            console.error(`Error starting ${genre} ebook concept generation:`, error);
            setEbookState(prev => ({ ...prev, status: 'error', message: `Network error starting ${genre} concept generation.`, error: String(error), current_genre: genre }));
        }
    };

    const handleApproveEbookConcept = async () => {
        if (!ebookState.proposed_title || !ebookState.proposed_premise) return;
        try {
            const response = await fetch(`${API_BASE_URL}/generate-ebook`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: ebookState.proposed_title, premise: ebookState.proposed_premise }),
            });
            const data = await response.json();
             if (!response.ok) {
                setEbookState(prev => ({ ...prev, status: 'error', message: data.error || `Error: ${response.statusText}`, error: data.error || 'Failed to start content generation.' }));
                return;
            }
            setEbookState(prev => ({ ...prev, status: 'running', message: data.message || 'Content generation started...' }));
            // Polling should already be running or will be restarted if stopped
            if (!ebookIntervalId.current) {
                 startPolling(`${API_BASE_URL}/status-ebook`, setEbookState, ebookIntervalId);
            }
        } catch (error) {
            console.error('Error starting ebook content generation:', error);
            setEbookState(prev => ({ ...prev, status: 'error', message: 'Network error starting content generation.', error: String(error) }));
        }
    };

    // Podcast Handlers
    const handleGeneratePodcastTopic = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/generate-podcast-topic`, {
                 method: 'POST',
                 headers: { 'Content-Type': 'application/json' },
                 body: JSON.stringify({ topic: podcastTopicInput || null }), // Send topic if provided
            });
            const data = await response.json();
             if (!response.ok) {
                setPodcastState(prev => ({ ...prev, status: 'error', message: data.error || `Error: ${response.statusText}`, error: data.error || 'Failed to start topic generation.' }));
                return;
            }
            // Backend handles setting status to generating_topic or awaiting_approval
            // We just need to start polling based on the response message
            setPodcastState(prev => ({ ...prev, message: data.message || 'Podcast process initiated...' }));
            startPolling(`${API_BASE_URL}/status-podcast`, setPodcastState, podcastIntervalId);
        } catch (error) {
            console.error('Error starting podcast topic generation:', error);
            setPodcastState(prev => ({ ...prev, status: 'error', message: 'Network error starting topic generation.', error: String(error) }));
        }
    };

     const handleApprovePodcastTopic = async () => {
        if (!podcastState.proposed_topic) return;
        try {
            const response = await fetch(`${API_BASE_URL}/generate-podcast`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ topic: podcastState.proposed_topic }),
            });
            const data = await response.json();
             if (!response.ok) {
                setPodcastState(prev => ({ ...prev, status: 'error', message: data.error || `Error: ${response.statusText}`, error: data.error || 'Failed to start content generation.' }));
                return;
            }
            setPodcastState(prev => ({ ...prev, status: 'generating_podcast', message: data.message || 'Content generation started...' }));
            // Ensure polling is active
             if (!podcastIntervalId.current) {
                 startPolling(`${API_BASE_URL}/status-podcast`, setPodcastState, podcastIntervalId);
            }
        } catch (error) {
            console.error('Error starting podcast content generation:', error);
            setPodcastState(prev => ({ ...prev, status: 'error', message: 'Network error starting content generation.', error: String(error) }));
        }
    };

    // Video Handlers
    const handleGenerateVideosForEpisode = async (episodeFilename: string) => {
        if (!episodeFilename) {
            setVideoState(prev => ({ ...prev, status: 'error', message: 'No episode filename provided.', error: 'No episode filename.' , current_episode: null}));
            return;
        }
        // Reset parts of video state for the new episode, but keep is_generating if already true for another
        setVideoState(prev => ({ 
            ...prev, 
            status: 'preparing_prompts', // Or 'generating_video' if prompts are assumed to exist or be quick
            message: `Starting video generation for ${episodeFilename}...`,
            current_episode: episodeFilename,
            video_filenames: [], // Clear previous episode's videos
            error: null 
        }));
        try {
            const response = await fetch(`${API_BASE_URL}/generate-videos-from-podcasts`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ episode_filename: episodeFilename }),
            });
            const data = await response.json();
            if (!response.ok) {
                setVideoState(prev => ({ ...prev, status: 'error', message: data.error || `Error: ${response.statusText}`, error: data.error || `Failed to start video generation for ${episodeFilename}.`, current_episode: episodeFilename }));
                return;
            }
            setVideoState(prev => ({ ...prev, message: data.message || `Video generation in progress for ${episodeFilename}...`, current_episode: episodeFilename }));
            startPolling(`${API_BASE_URL}/status-video`, setVideoState, videoIntervalId);
        } catch (error) {
            console.error(`Error starting video generation for ${episodeFilename}:`, error);
            setVideoState(prev => ({ ...prev, status: 'error', message: `Network error starting video generation for ${episodeFilename}.`, error: String(error), current_episode: episodeFilename }));
        }
    };

    // --- Render Logic ---

    // Helper to get status color
    const getStatusColor = (status: string): string => {
        if (status.includes('generating') || status.includes('running')) return 'text-yellow-600 dark:text-yellow-400';
        if (status === 'awaiting_approval') return 'text-orange-600 dark:text-orange-400';
        if (status === 'completed') return 'text-green-600 dark:text-green-400';
        if (status === 'error') return 'text-red-600 dark:text-red-400';
        return 'text-gray-600 dark:text-gray-400'; // idle or other
    };

    // Helper for button styling
    const baseButtonClass = "px-4 py-2 rounded-md font-semibold text-sm transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-gray-900";
    const primaryButtonClass = `${baseButtonClass} bg-indigo-600 text-white hover:bg-indigo-700 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed`;
    const secondaryButtonClass = `${baseButtonClass} bg-gray-200 text-gray-800 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600 focus:ring-gray-500 disabled:opacity-50 disabled:cursor-not-allowed`;
    const successButtonClass = `${baseButtonClass} bg-green-600 text-white hover:bg-green-700 focus:ring-green-500 disabled:opacity-50 disabled:cursor-not-allowed`;
    const warningButtonClass = `${baseButtonClass} bg-yellow-500 text-white hover:bg-yellow-600 focus:ring-yellow-400 disabled:opacity-50 disabled:cursor-not-allowed`;

    const renderEbookSection = () => {
        const isProcessing = ebookState.status === 'generating_concept' || ebookState.status === 'running';
        const isAwaiting = ebookState.status === 'awaiting_approval';
        const isIdle = ebookState.status === 'idle';

        return (
            <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-lg w-full max-w-lg border border-gray-200 dark:border-gray-700 flex flex-col gap-4">
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Ebook Generator</h2>
                <div className="text-sm">
                    <span className="font-medium text-gray-700 dark:text-gray-300">Status: </span>
                    <span className={`font-semibold ${getStatusColor(ebookState.status)}`}>{ebookState.status.replace(/_/g, ' ')}</span>
                </div>
                <p className="text-gray-600 dark:text-gray-400 text-sm min-h-[40px]">{ebookState.message}</p>

                {isIdle && (
                    <div className="flex flex-col sm:flex-row gap-3">
                        <button onClick={() => handleGenerateEbookConcept('Thriller')} className={primaryButtonClass} disabled={isProcessing}>
                            Generate Thriller Concept
                        </button>
                        <button onClick={() => handleGenerateEbookConcept('Romance')} className={primaryButtonClass} disabled={isProcessing}>
                            Generate Romance Concept
                        </button>
                    </div>
                )}

                {isAwaiting && ebookState.proposed_title && (
                    <div className="mt-2 p-4 border border-gray-200 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700/50 space-y-3">
                        <h3 className="font-semibold text-gray-800 dark:text-gray-200">Proposed {ebookState.current_genre || 'Ebook'} Concept:</h3>
                        <p className="text-sm"><strong className="font-medium text-gray-700 dark:text-gray-300">Title:</strong> <span className="text-gray-600 dark:text-gray-400">{ebookState.proposed_title}</span></p>
                        <p className="text-sm"><strong className="font-medium text-gray-700 dark:text-gray-300">Premise:</strong> <span className="text-gray-600 dark:text-gray-400">{ebookState.proposed_premise}</span></p>
                        {ebookState.current_genre && <p className="text-xs text-gray-500 dark:text-gray-400">Genre: {ebookState.current_genre}</p>}
                        <div className="mt-3 flex flex-col sm:flex-row gap-3">
                            <button onClick={handleApproveEbookConcept} className={successButtonClass} disabled={isProcessing}>
                                Approve & Generate {ebookState.current_genre || 'Ebook'}
                            </button>
                            <button 
                                onClick={() => handleGenerateEbookConcept(ebookState.current_genre || 'Thriller')} 
                                className={warningButtonClass} 
                                disabled={isProcessing}
                            >
                                Request New {ebookState.current_genre || ''} Concept
                            </button>
                        </div>
                    </div>
                )}

                {isProcessing && (
                    <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400 italic text-sm">
                        <svg className="animate-spin h-4 w-4 text-indigo-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Processing... please wait.
                    </div>
                )}

                {ebookState.status === 'completed' && ebookState.pdf_filename && (
                    <div className="mt-2 space-y-2">
                        <p className="text-green-600 dark:text-green-400 font-semibold text-sm">Ebook generation complete!</p>
                        <a
                            href={`${API_BASE_URL}/download/${ebookState.pdf_filename}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-2 text-indigo-600 dark:text-indigo-400 hover:underline text-sm font-medium"
                        >
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                            </svg>
                            Download "{ebookState.pdf_filename}" ({ebookState.current_genre || 'Ebook'})
                        </a>
                         <button onClick={() => setEbookState({ is_generating: false, status: 'idle', message: 'Ready for Ebook generation.', proposed_title: null, proposed_premise: null, current_genre: null, pdf_filename: null, error: null })} className={secondaryButtonClass}>
                            Start New Ebook
                        </button>
                    </div>
                )}

                {ebookState.status === 'error' && (
                     <div className="mt-2 space-y-2">
                        <p className="text-red-600 dark:text-red-400 text-sm font-medium">Error ({ebookState.current_genre || 'Ebook'}): {ebookState.error || 'An unknown error occurred.'}</p>
                         <button onClick={() => setEbookState({ is_generating: false, status: 'idle', message: 'Ready for Ebook generation.', proposed_title: null, proposed_premise: null, current_genre: null, pdf_filename: null, error: null })} className={secondaryButtonClass}>
                            Try Again
                        </button>
                    </div>
                )}
            </div>
        );
    };

    const renderPodcastSection = () => {
        const isProcessing = podcastState.status === 'generating_topic' || podcastState.status === 'generating_podcast';
        const isAwaiting = podcastState.status === 'awaiting_approval';
        const isIdle = podcastState.status === 'idle';

        return (
            <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-lg w-full max-w-lg border border-gray-200 dark:border-gray-700 flex flex-col gap-4">
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Tech Podcast Generator</h2>
                <div className="text-sm">
                    <span className="font-medium text-gray-700 dark:text-gray-300">Status: </span>
                    <span className={`font-semibold ${getStatusColor(podcastState.status)}`}>{podcastState.status.replace(/_/g, ' ')}</span>
                </div>
                <p className="text-gray-600 dark:text-gray-400 text-sm min-h-[40px]">{podcastState.message}</p>

                {isIdle && (
                    <div className="flex flex-col gap-3">
                        <input
                            type="text"
                            value={podcastTopicInput}
                            onChange={(e) => setPodcastTopicInput(e.target.value)}
                            placeholder="Optional: Enter specific topic"
                            className="border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-200 focus:ring-indigo-500 focus:border-indigo-500"
                            disabled={isProcessing}
                        />
                        <button
                            onClick={handleGeneratePodcastTopic}
                            className={primaryButtonClass}
                            disabled={isProcessing}
                        >
                            {podcastTopicInput ? 'Propose My Topic' : 'Generate Podcast Topic'}
                        </button>
                    </div>
                )}

                {isAwaiting && podcastState.proposed_topic && (
                    <div className="mt-2 p-4 border border-gray-200 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700/50 space-y-3">
                        <h3 className="font-semibold text-gray-800 dark:text-gray-200">Proposed Topic:</h3>
                        <p className="text-sm"><strong className="font-medium text-gray-700 dark:text-gray-300">Topic:</strong> <span className="text-gray-600 dark:text-gray-400">{podcastState.proposed_topic}</span></p>
                        <div className="mt-3 flex flex-col sm:flex-row gap-3">
                            <button onClick={handleApprovePodcastTopic} className={successButtonClass} disabled={isProcessing}>
                                Approve & Generate Podcast
                            </button>
                            <button onClick={() => { setPodcastTopicInput(''); handleGeneratePodcastTopic(); }} className={warningButtonClass} disabled={isProcessing}>
                                Request New Topic
                            </button>
                        </div>
                    </div>
                )}

                {isProcessing && (
                     <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400 italic text-sm">
                        <svg className="animate-spin h-4 w-4 text-indigo-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Processing... please wait.
                    </div>
                )}

                {podcastState.status === 'completed' && podcastState.pdf_filenames && podcastState.pdf_filenames.length > 0 && (
                    <div className="mt-2 space-y-2">
                        <p className="text-green-600 dark:text-green-400 font-semibold text-sm">Podcast generation complete!</p>
                        <ul className="space-y-1">
                            {podcastState.pdf_filenames.map((filename) => (
                                <li key={filename}>
                                    <a
                                        href={`${API_BASE_URL}/download/${filename}`}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center gap-2 text-indigo-600 dark:text-indigo-400 hover:underline text-sm font-medium"
                                    >
                                         <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                            <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                        </svg>
                                        Download "{filename}"
                                    </a>
                                </li>
                            ))}
                        </ul>
                         <button onClick={() => setPodcastState({ is_generating: false, status: 'idle', message: 'Ready for Podcast generation.', proposed_topic: null, pdf_filenames: [], error: null })} className={secondaryButtonClass}>
                            Start New Podcast
                        </button>
                    </div>
                )}

                {podcastState.status === 'error' && (
                     <div className="mt-2 space-y-2">
                        <p className="text-red-600 dark:text-red-400 text-sm font-medium">Error: {podcastState.error || 'An unknown error occurred.'}</p>
                         <button onClick={() => setPodcastState({ is_generating: false, status: 'idle', message: 'Ready for Podcast generation.', proposed_topic: null, pdf_filenames: [], error: null })} className={secondaryButtonClass}>
                            Try Again
                        </button>
                    </div>
                )}
            </div>
        );
    };

    // Added Video Section Renderer
    const renderVideoSection = () => {
        const isProcessingAnyVideo = videoState.is_generating;
        
        return (
            <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-lg w-full max-w-lg border border-gray-200 dark:border-gray-700 flex flex-col gap-4">
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Video Generator (Per Episode)</h2>
                <div className="text-sm">
                    <span className="font-medium text-gray-700 dark:text-gray-300">Overall Status: </span>
                    <span className={`font-semibold ${getStatusColor(videoState.status)}`}>
                        {videoState.status.replace(/_/g, ' ')}
                        {videoState.current_episode && ` for ${videoState.current_episode}`}
                    </span>
                </div>
                <p className="text-gray-600 dark:text-gray-400 text-sm min-h-[40px]">{videoState.message}</p>

                <button 
                    onClick={fetchPodcastEpisodes} 
                    className={`${secondaryButtonClass} mb-3`} // Added mb-3 for spacing
                    disabled={videoState.is_generating} // Disable if any video processing is active
                >
                    Refresh Podcast Episode List
                </button>

                {podcastEpisodes.length === 0 && videoState.status === 'idle' && (
                    <p className="text-sm text-gray-500 dark:text-gray-400">No podcast episodes found. Generate a podcast first, or try refreshing the list.</p>
                )}

                <div className="space-y-3 max-h-60 overflow-y-auto pr-2">
                    {podcastEpisodes.map((episode) => (
                        <div key={episode.filename} className="p-3 border border-gray-200 dark:border-gray-700 rounded-md bg-gray-50 dark:bg-gray-700/50">
                            <p className="font-medium text-sm text-gray-800 dark:text-gray-200 truncate" title={episode.filename}>{episode.filename}</p>
                            <p className="text-xs text-gray-500 dark:text-gray-400">
                                Prompts: {episode.has_prompts ? 'Generated' : 'Not generated'}
                            </p>
                            <button
                                onClick={() => handleGenerateVideosForEpisode(episode.filename)}
                                className={`${primaryButtonClass} mt-2 w-full text-xs`}
                                disabled={isProcessingAnyVideo && videoState.current_episode !== episode.filename} // Disable if another episode is processing
                            >
                                {isProcessingAnyVideo && videoState.current_episode === episode.filename ? 'Processing...' : `Generate Videos for this Episode`}
                            </button>
                        </div>
                    ))}
                </div>
                
                {videoState.status === 'completed' && videoState.current_episode && videoState.video_filenames && videoState.video_filenames.length > 0 && (
                    <div className="mt-2 space-y-2">
                        <p className="text-green-600 dark:text-green-400 font-semibold text-sm">Video generation complete for {videoState.current_episode}!</p>
                        <ul className="space-y-1">
                            {videoState.video_filenames.map((filename) => (
                                <li key={filename}>
                                    <a
                                        href={`${API_BASE_URL}/download/${filename}`}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center gap-2 text-indigo-600 dark:text-indigo-400 hover:underline text-sm font-medium"
                                    >
                                         <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                            <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                        </svg>
                                        Download "{filename}"
                                    </a>
                                </li>
                            ))}
                        </ul>
                         <button onClick={() => {
                             setVideoState({ is_generating: false, status: 'idle', message: 'Ready for Video generation.', proposed_topic: null, video_filenames: [], error: null, current_episode: null });
                             fetchPodcastEpisodes(); // Refresh list in case new episodes were added
                            }} className={secondaryButtonClass}>
                            Back to Episode List
                        </button>
                    </div>
                )}

                 {videoState.status === 'error' && videoState.current_episode && (
                     <div className="mt-2 space-y-2">
                        <p className="text-red-600 dark:text-red-400 text-sm font-medium">Error during video generation for {videoState.current_episode}: {videoState.error || 'An unknown error occurred.'}</p>
                         <button onClick={() => {
                             setVideoState({ is_generating: false, status: 'idle', message: 'Ready for Video generation.', proposed_topic: null, video_filenames: [], error: null, current_episode: null });
                             fetchPodcastEpisodes(); // Refresh list
                            }} className={secondaryButtonClass}>
                            Try Another Episode
                        </button>
                    </div>
                )}
            </div>
        );
    };


    return (
        <div className="flex flex-col items-center min-h-screen p-4 sm:p-8 gap-10 bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100 font-sans">
            <h1 className="text-3xl sm:text-4xl font-bold text-center mt-4">AI Content Generator</h1>
            <div className="flex flex-col lg:flex-row gap-8 w-full max-w-6xl justify-center items-start">
                {renderEbookSection()}
                {renderPodcastSection()}
                {renderVideoSection()} {/* Added video section */}
            </div>
            {/* Optional: Add section for Trending Podcasts if needed later */}
        </div>
    );
}
