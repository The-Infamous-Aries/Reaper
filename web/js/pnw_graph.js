// Politics & War Graph JavaScript

class PNWGraphManager {
    constructor() {
        this.currentGraphType = null;
        this.currentGraphParams = {};
        this.graphForms = {
            war: this.createWarForm(),
            warnet: this.createWarNetForm(),
            compare: this.createCompareForm(),
            treaty: this.createTreatyForm(),
            stocks: this.createStocksForm()
        };
        
        this.init();
    }

    init() {
        console.log('PNWGraphManager initializing...');
        this.setupEventListeners();
        this.setupNavigation();
        this.showWelcomeState();
        console.log('PNWGraphManager initialized successfully');
    }

    setupEventListeners() {
        console.log('Setting up event listeners...');
        // Graph type selection from emoji buttons
        document.querySelectorAll('.graph-emoji-button').forEach(button => {
            console.log('Found button:', button);
            button.addEventListener('click', (e) => {
                console.log('Button clicked:', e.target);
                e.preventDefault();
                const graphType = e.target.closest('.graph-emoji-button').dataset.graphType;
                console.log('Graph type selected:', graphType);
                if (graphType) {
                    this.selectGraphType(graphType);
                }
            });
        });
        console.log('Event listeners setup complete');

        // Dashboard navigation from right sidebar
        document.querySelectorAll('.dashboard-sidebar .nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = e.target.closest('.nav-link').dataset.page;
                if (page && page !== 'graphs') {
                    this.navigateToPage(page);
                }
            });
        });

        // Configuration panel close button
        document.getElementById('btn-close-config').addEventListener('click', () => {
            this.hideConfiguration();
        });

        // Graph display controls
        document.getElementById('btn-regenerate').addEventListener('click', () => {
            this.generateGraph();
        });

        document.getElementById('btn-configure').addEventListener('click', () => {
            this.showConfiguration();
        });

        document.getElementById('btn-back-to-config').addEventListener('click', () => {
            this.showConfiguration();
        });

        // Form submission handling (delegated)
        document.getElementById('config-body').addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleFormSubmission(e.target);
        });
    }

    setupNavigation() {
        // Handle browser back/forward buttons
        window.addEventListener('popstate', (e) => {
            if (e.state && e.state.graphType) {
                this.selectGraphType(e.state.graphType, false);
            } else {
                this.showWelcomeState();
            }
        });
    }

    selectGraphType(graphType, updateHistory = true) {
        this.currentGraphType = graphType;
        
        // Update button active state
        document.querySelectorAll('.graph-emoji-button').forEach(button => {
            button.classList.remove('active');
        });
        document.querySelector(`.graph-emoji-button[data-graph-type="${graphType}"]`).classList.add('active');

        // Update browser history
        if (updateHistory) {
            const url = new URL(window.location);
            url.searchParams.set('type', graphType);
            window.history.pushState({ graphType }, '', url);
        }

        // Show configuration for this graph type
        this.showConfiguration(graphType);
    }

    showConfiguration(graphType = null) {
        const type = graphType || this.currentGraphType;
        if (!type) return;

        // Hide other states
        this.hideAllStates();

        // Show configuration panel
        const configPanel = document.getElementById('graph-config-panel');
        const configTitle = document.getElementById('config-title');
        const configBody = document.getElementById('config-body');

        configPanel.style.display = 'block';
        configPanel.classList.add('fade-in');

        // Set title and form
        configTitle.textContent = this.getGraphTitle(type);
        configBody.innerHTML = this.graphForms[type];

        // Update page title (with null check)
        const pageSubtitle = document.querySelector('.page-subtitle');
        if (pageSubtitle) {
            pageSubtitle.textContent = `Configure ${this.getGraphTitle(type)}`;
        }
    }

    hideConfiguration() {
        document.getElementById('graph-config-panel').style.display = 'none';
        this.showWelcomeState();
    }

    handleFormSubmission(form) {
        const formData = new FormData(form);
        const params = Object.fromEntries(formData.entries());
        
        // Add the graph type
        params.type = this.currentGraphType;

        // Store parameters for regeneration
        this.currentGraphParams = params;

        // Generate the graph
        this.generateGraph();
    }

    generateGraph() {
        if (!this.currentGraphType || !this.currentGraphParams) return;

        // Hide configuration and show display area
        this.hideAllStates();
        this.showGraphDisplay();

        // Show loading state
        this.showLoadingState();

        // Build API URL
        const queryString = new URLSearchParams(this.currentGraphParams).toString();
        const apiUrl = `/api/graph/${this.currentGraphType}?${queryString}`;

        // Simulate progress for better UX
        this.simulateProgress();

        // Fetch graph data
        fetch(apiUrl)
            .then(response => {
                if (!response.ok) {
                    return response.text().then(text => {
                        throw new Error(`Failed to load graph: ${text || response.statusText}`);
                    });
                }
                return response.text();
            })
            .then(graphData => {
                this.displayGraph(graphData);
            })
            .catch(error => {
                this.showError(error.message);
            });
    }

    showGraphDisplay() {
        const displayArea = document.getElementById('graph-display-area');
        displayArea.style.display = 'flex';
        displayArea.classList.add('fade-in');

        // Update title
        document.getElementById('graph-display-title').textContent = 
            `Generating ${this.getGraphTitle(this.currentGraphType)}...`;
    }

    showLoadingState() {
        document.getElementById('graph-loading').style.display = 'block';
        document.getElementById('graph-error').style.display = 'none';
        document.getElementById('graph-result').style.display = 'none';
    }

    simulateProgress() {
        const progressBar = document.getElementById('progress-bar');
        const loadingText = document.getElementById('loading-text');
        
        const progressSteps = this.getProgressSteps(this.currentGraphType);
        
        let currentStep = 0;
        const interval = setInterval(() => {
            if (currentStep < progressSteps.length) {
                const step = progressSteps[currentStep];
                progressBar.style.width = step.progress + '%';
                loadingText.textContent = step.text;
                currentStep++;
            } else {
                clearInterval(interval);
            }
        }, 800);
    }

    displayGraph(graphData) {
        const resultContainer = document.getElementById('graph-result');
        const loadingContainer = document.getElementById('graph-loading');
        
        loadingContainer.style.display = 'none';
        resultContainer.style.display = 'block';

        // Update title
        document.getElementById('graph-display-title').textContent = 
            this.getGraphTitle(this.currentGraphType);

        // Display the graph
        if (graphData.includes('<html') || graphData.includes('<!DOCTYPE')) {
            // HTML content (Plotly graphs)
            resultContainer.innerHTML = 
                `<iframe srcdoc="${graphData.replace(/"/g, '&quot;')}" class="graph-iframe"></iframe>`;
        } else {
            // Image data (base64)
            resultContainer.innerHTML = 
                `<img src="data:image/png;base64,${graphData}" class="graph-image" alt="Generated Graph">`;
        }
    }

    showError(message) {
        document.getElementById('graph-loading').style.display = 'none';
        document.getElementById('graph-error').style.display = 'block';
        document.getElementById('error-message').textContent = message;
    }

    showWelcomeState() {
        this.hideAllStates();
        document.getElementById('welcome-state').style.display = 'flex';
        
        // Update page title (with null check)
        const pageSubtitle = document.querySelector('.page-subtitle');
        if (pageSubtitle) {
            pageSubtitle.textContent = 'Select a graph type from the left menu to begin analysis';
        }
    }

    hideAllStates() {
        document.getElementById('welcome-state').style.display = 'none';
        document.getElementById('graph-config-panel').style.display = 'none';
        document.getElementById('graph-display-area').style.display = 'none';
    }

    navigateToPage(page) {
        // Navigate to dashboard pages
        window.location.href = `/dashboard.html?page=${page}`;
    }

    // Form creation methods
    createWarForm() {
        return `
            <form id="war-form" class="graph-form">
                <div class="row">
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label for="alliance_name" class="form-label">Alliance Name or ID</label>
                            <input type="text" class="form-control" id="alliance_name" name="alliance_name" 
                                   placeholder="e.g., The Knights Radiant or 1234" required>
                            <div class="form-text">Enter the alliance name or ID to analyze</div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label for="time" class="form-label">Time Range</label>
                            <input type="text" class="form-control" id="time" name="time" 
                                   placeholder="e.g., 2d, 3w, 1m" value="7d" required>
                            <div class="form-text">d=days, w=weeks, m=months (e.g., '2d' for last 2 days)</div>
                        </div>
                    </div>
                </div>
                
                <div class="row">
                    <div class="col-md-6">
                        <div class="mb-3">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="force_refresh" name="force_refresh">
                                <label class="form-check-label" for="force_refresh">Force Refresh Data</label>
                            </div>
                            <div class="form-text">Bypass cache and fetch fresh data</div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="mb-3">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="opps_view" name="opps_view">
                                <label class="form-check-label" for="opps_view">Opponent's Perspective</label>
                            </div>
                            <div class="form-text">View from the opponent's side</div>
                        </div>
                    </div>
                </div>
                
                <div class="text-center">
                    <button type="submit" class="btn btn-gold">
                        <i class="fas fa-chart-pie"></i> Generate War Analysis
                    </button>
                </div>
            </form>
        `;
    }

    createWarNetForm() {
        return `
            <form id="warnet-form" class="graph-form">
                <div class="row">
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label for="alliance_name" class="form-label">Alliance Name or ID</label>
                            <input type="text" class="form-control" id="alliance_name" name="alliance_name" 
                                   placeholder="e.g., The Knights Radiant or 1234" required>
                            <div class="form-text">Enter the alliance name or ID to analyze</div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label for="time" class="form-label">Time Range</label>
                            <input type="text" class="form-control" id="time" name="time" 
                                   placeholder="e.g., 2d, 3w, 1m" value="7d" required>
                            <div class="form-text">d=days, w=weeks, m=months</div>
                        </div>
                    </div>
                </div>
                
                <div class="row">
                    <div class="col-md-6">
                        <div class="mb-3">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="force_refresh" name="force_refresh">
                                <label class="form-check-label" for="force_refresh">Force Refresh Data</label>
                            </div>
                            <div class="form-text">Bypass cache and fetch fresh data</div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="mb-3">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="opps_view" name="opps_view">
                                <label class="form-check-label" for="opps_view">Opponent's Perspective</label>
                            </div>
                            <div class="form-text">View from the opponent's side</div>
                        </div>
                    </div>
                </div>
                
                <div class="text-center">
                    <button type="submit" class="btn btn-gold">
                        <i class="fas fa-project-diagram"></i> Generate Net Analysis
                    </button>
                </div>
            </form>
        `;
    }

    createCompareForm() {
        return `
            <form id="compare-form" class="graph-form">
                <div class="row">
                    <div class="col-md-6">
                        <h5 class="text-gold mb-3">
                            <i class="fas fa-home"></i> Home Alliance(s)
                        </h5>
                        <div class="mb-3">
                            <label for="home_alliance_ids" class="form-label">Alliance IDs</label>
                            <input type="text" class="form-control" id="home_alliance_ids" name="home_alliance_ids" 
                                   placeholder="e.g., 1234, 5678" required>
                            <div class="form-text">Comma-separated alliance IDs</div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <h5 class="text-gold mb-3">
                            <i class="fas fa-crosshairs"></i> Away Alliance(s)
                        </h5>
                        <div class="mb-3">
                            <label for="away_alliance_ids" class="form-label">Alliance IDs</label>
                            <input type="text" class="form-control" id="away_alliance_ids" name="away_alliance_ids" 
                                   placeholder="e.g., 9012, 3456" required>
                            <div class="form-text">Comma-separated alliance IDs</div>
                        </div>
                    </div>
                </div>
                
                <div class="text-center">
                    <button type="submit" class="btn btn-gold">
                        <i class="fas fa-balance-scale"></i> Generate Comparison
                    </button>
                </div>
            </form>
        `;
    }

    createTreatyForm() {
        return `
            <form id="treaty-form" class="graph-form">
                <div class="mb-3">
                    <label for="alliance_ids" class="form-label">Alliance IDs (Optional)</label>
                    <input type="text" class="form-control" id="alliance_ids" name="alliance_ids" 
                           placeholder="e.g., 1234, 5678 (leave blank for all)">
                    <div class="form-text">
                        Focus on specific alliances or leave blank to show the entire treaty universe
                    </div>
                </div>
                
                <div class="text-center">
                    <button type="submit" class="btn btn-gold">
                        <i class="fas fa-globe"></i> Generate Treaty Map
                    </button>
                </div>
            </form>
        `;
    }

    createStocksForm() {
        return `
            <form id="stocks-form" class="graph-form">
                <div class="alert alert-info">
                    <h5><i class="fas fa-info-circle"></i> Stock Market Analysis</h5>
                    <p>This graph shows trends for Politics & War stock market resources including Steel, Aluminum, Gasoline, Munitions, and Food.</p>
                </div>
                
                <div class="text-center">
                    <button type="submit" class="btn btn-gold">
                        <i class="fas fa-chart-line"></i> Generate Stock Trends
                    </button>
                </div>
            </form>
        `;
    }

    // Utility methods
    getGraphTitle(type) {
        const titles = {
            war: 'War Cost Breakdown',
            warnet: 'War Net Analysis',
            compare: 'Alliance Comparison',
            treaty: 'Treaty Universe',
            stocks: 'Stock Market Trends'
        };
        return titles[type] || 'Unknown Graph';
    }

    getProgressSteps(type) {
        const steps = {
            war: [
                { progress: 20, text: 'Connecting to Politics & War API...' },
                { progress: 40, text: 'Fetching war data...' },
                { progress: 60, text: 'Calculating costs...' },
                { progress: 80, text: 'Generating chart...' },
                { progress: 95, text: 'Finalizing display...' }
            ],
            warnet: [
                { progress: 20, text: 'Connecting to Politics & War API...' },
                { progress: 40, text: 'Fetching war networks...' },
                { progress: 60, text: 'Analyzing relationships...' },
                { progress: 80, text: 'Building network map...' },
                { progress: 95, text: 'Rendering visualization...' }
            ],
            compare: [
                { progress: 20, text: 'Fetching alliance data...' },
                { progress: 40, text: 'Comparing statistics...' },
                { progress: 60, text: 'Calculating metrics...' },
                { progress: 80, text: 'Creating comparison chart...' },
                { progress: 95, text: 'Finalizing display...' }
            ],
            treaty: [
                { progress: 20, text: 'Fetching treaty data...' },
                { progress: 40, text: 'Building alliance network...' },
                { progress: 60, text: 'Mapping relationships...' },
                { progress: 80, text: 'Creating 3D visualization...' },
                { progress: 95, text: 'Rendering universe...' }
            ],
            stocks: [
                { progress: 25, text: 'Loading market data...' },
                { progress: 50, text: 'Analyzing trends...' },
                { progress: 75, text: 'Creating charts...' },
                { progress: 95, text: 'Finalizing display...' }
            ]
        };
        return steps[type] || steps.war;
    }
}

// Initialize the graph manager when the dashboard page is loaded
document.addEventListener('dashboardPageLoaded', (event) => {
    console.log('Dashboard page loaded event:', event.detail);
    if (event.detail.page === 'graphs.html') {
        console.log('Initializing PNWGraphManager for graphs page');
        window.pnwGraphManager = new PNWGraphManager();
    }
});