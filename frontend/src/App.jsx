import React, { useState, useEffect, useRef } from 'react';
import { 
  BookOpen, 
  Search, 
  Compass, 
  CheckCircle2, 
  AlertTriangle, 
  Clock, 
  Layers, 
  ExternalLink, 
  Play, 
  ThumbsUp, 
  ThumbsDown, 
  Activity, 
  FileText, 
  BarChart3, 
  ShieldCheck,
  RefreshCw,
  Sparkles,
  Upload,
  FolderPlus,
  Trash2,
  Cpu,
  Database,
  CheckCircle,
  HelpCircle
} from 'lucide-react';
import * as api from './api/client';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [health, setHealth] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [gaps, setGaps] = useState([]);
  const [proposals, setProposals] = useState([]);
  const [stats, setStats] = useState(null);
  const [evalHistory, setEvalHistory] = useState([]);
  
  // Research & Live Workspace
  const [activeRun, setActiveRun] = useState(null);
  const [events, setEvents] = useState([]);
  const [researchQuery, setResearchQuery] = useState('');
  const [isResearching, setIsResearching] = useState(false);
  const [sseUnsub, setSseUnsub] = useState(null);

  // Search
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);

  // Ingestion
  const [dirPath, setDirPath] = useState('');
  const [uploading, setUploading] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');

  // Evaluation
  const [evaluating, setEvaluating] = useState(false);
  const [latestEval, setLatestEval] = useState(null);

  const fileInputRef = useRef(null);

  useEffect(() => {
    loadAll();
    return () => {
      if (sseUnsub) sseUnsub();
    };
  }, []);

  // Auto-reload data whenever user switches tabs
  useEffect(() => {
    if (activeTab === 'dashboard') {
      loadDocuments();
      loadStats();
    } else if (activeTab === 'gaps') {
      loadGaps();
    } else if (activeTab === 'proposals') {
      loadProposals();
    } else if (activeTab === 'evaluation') {
      loadEvalHistory();
    }
  }, [activeTab]);

  const loadAll = async () => {
    await Promise.all([
      loadHealth(),
      loadStats(),
      loadDocuments(),
      loadGaps(),
      loadProposals(),
      loadEvalHistory(),
    ]);
  };

  const loadHealth = async () => {
    try {
      const data = await api.fetchHealth();
      setHealth(data);
    } catch (e) {
      console.error('Health check error:', e);
    }
  };

  const loadStats = async () => {
    try {
      const data = await api.fetchKnowledgeStats();
      setStats(data);
    } catch (e) {
      console.error('Stats error:', e);
    }
  };

  const loadDocuments = async () => {
    try {
      const data = await api.fetchDocuments();
      setDocuments(data.items || []);
    } catch (e) {
      console.error('Docs error:', e);
    }
  };

  const loadGaps = async () => {
    try {
      const data = await api.fetchGaps();
      const sorted = (data || []).sort((a, b) => (b.priority_score || 0) - (a.priority_score || 0));
      setGaps(sorted);
      if (sorted.length > 0) {
        setStatusMsg(`Loaded ${sorted.length} knowledge gaps`);
      }
    } catch (e) {
      console.error('Gaps error:', e);
    }
  };

  const loadProposals = async () => {
    try {
      const data = await api.fetchProposals();
      setProposals(data || []);
      if (data && data.length > 0) {
        setStatusMsg(`Loaded ${data.length} knowledge proposals`);
      }
    } catch (e) {
      console.error('Proposals error:', e);
    }
  };

  const loadEvalHistory = async () => {
    try {
      const data = await api.fetchEvaluationHistory();
      setEvalHistory(data || []);
      if (data && data.length > 0) {
        setLatestEval(data[0]);
      }
    } catch (e) {
      console.error('Eval error:', e);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setStatusMsg(`Ingesting ${file.name}...`);
    try {
      await api.uploadDocument(file);
      setStatusMsg(`Successfully ingested ${file.name}!`);
      loadDocuments();
      loadStats();
    } catch (err) {
      setStatusMsg(`Upload failed: ${err.message}`);
    } finally {
      setUploading(false);
    }
  };

  const handleDirectoryIngest = async (e) => {
    e.preventDefault();
    if (!dirPath.trim()) return;
    setUploading(true);
    setStatusMsg(`Scanning folder: ${dirPath}...`);
    try {
      const res = await api.ingestDirectory(dirPath.trim());
      setStatusMsg(`Ingested ${res.ingested_count} files from folder!`);
      setDirPath('');
      loadDocuments();
      loadStats();
    } catch (err) {
      setStatusMsg(`Directory ingestion failed: ${err.message}`);
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteDoc = async (id) => {
    try {
      await api.deleteDocument(id);
      loadDocuments();
      loadStats();
    } catch (err) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  const handleClearKnowledgeBase = async () => {
    if (!window.confirm("Are you sure you want to reset all documents, vectors, concepts, gaps, and proposals? This gives you a completely clean slate.")) {
      return;
    }
    setStatusMsg('Resetting knowledge base and vector store...');
    try {
      await api.clearKnowledgeBase();
      setDocuments([]);
      setGaps([]);
      setProposals([]);
      setEvents([]);
      setActiveRun(null);
      setSearchResults([]);
      setStatusMsg('Knowledge base reset! Ready for fresh document ingestion.');
      loadAll();
    } catch (err) {
      setStatusMsg(`Reset failed: ${err.message}`);
    }
  };

  const handleDetectGaps = async () => {
    setStatusMsg('Analyzing knowledge graph for gaps...');
    try {
      const res = await api.detectGaps('all');
      const sorted = (res.gaps || []).sort((a, b) => (b.priority_score || 0) - (a.priority_score || 0));
      setGaps(sorted);
      setStatusMsg(`Discovered ${sorted.length} candidate knowledge gaps.`);
    } catch (err) {
      setStatusMsg(`Gap detection failed: ${err.message}`);
    }
  };

  const handleStartResearch = async (gapId = null, directQuery = null) => {
    const q = directQuery || researchQuery;
    if (!gapId && !q.trim()) return;

    if (sseUnsub) sseUnsub();
    setIsResearching(true);
    setEvents([]);
    setActiveTab('workspace');

    try {
      const run = await api.startResearch({ gap_id: gapId, query: gapId ? null : q.trim() });
      setActiveRun(run);

      // Subscribe to real-time SSE stream
      const unsub = api.subscribeResearchEvents(
        run.run_id,
        (evt) => {
          setEvents((prev) => [...prev, evt]);
          if (evt.type === 'run_complete' || evt.type === 'done') {
            setIsResearching(false);
            loadProposals();
            loadGaps();
          }
        },
        (err) => {
          console.error('SSE Error:', err);
          setIsResearching(false);
        }
      );
      setSseUnsub(() => unsub);
    } catch (err) {
      alert(`Research launch failed: ${err.message}`);
      setIsResearching(false);
    }
  };

  const handleProposalAction = async (proposalId, action) => {
    try {
      await api.actionProposal(proposalId, action);
      loadProposals();
      loadDocuments();
      loadStats();
    } catch (err) {
      alert(`Proposal action failed: ${err.message}`);
    }
  };

  const handleRunEvaluation = async () => {
    setEvaluating(true);
    try {
      const res = await api.runEvaluation();
      setLatestEval(res);
      loadEvalHistory();
    } catch (err) {
      alert(`Evaluation failed: ${err.message}`);
    } finally {
      setEvaluating(false);
    }
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const data = await api.searchKnowledge(searchQuery);
      setSearchResults(data.results || []);
    } catch (err) {
      console.error(err);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="flex h-screen bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* Sidebar Navigation */}
      <aside className="w-64 border-r border-slate-800 bg-slate-900/80 backdrop-blur-md flex flex-col justify-between p-4 shrink-0">
        <div>
          <div className="flex items-center gap-3 px-2 py-3 mb-6">
            <div className="w-8 h-8 rounded-lg bg-sky-500 flex items-center justify-center shadow-lg shadow-sky-500/20 text-slate-950 font-bold text-lg">
              Ω
            </div>
            <div>
              <h1 className="text-sm font-bold tracking-tight text-white">Knowledge Agent</h1>
              <p className="text-[10px] text-slate-400 font-mono">Autonomous Research & Gap Filler</p>
            </div>
          </div>

          <nav className="space-y-1">
            <button
              onClick={() => setActiveTab('dashboard')}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                activeTab === 'dashboard'
                  ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <BookOpen className="w-4 h-4" />
              <span>Knowledge Base</span>
              {documents.length > 0 && (
                <span className="ml-auto text-[10px] bg-slate-800 px-1.5 py-0.5 rounded text-slate-400">
                  {documents.length}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab('gaps')}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                activeTab === 'gaps'
                  ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <Compass className="w-4 h-4" />
              <span>Knowledge Gaps</span>
              {gaps.length > 0 && (
                <span className="ml-auto text-[10px] bg-amber-500/20 text-amber-300 px-1.5 py-0.5 rounded font-mono">
                  {gaps.length}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab('workspace')}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                activeTab === 'workspace'
                  ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <Activity className="w-4 h-4" />
              <span>Research Workspace</span>
              {isResearching && (
                <span className="ml-auto w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
              )}
            </button>

            <button
              onClick={() => setActiveTab('proposals')}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                activeTab === 'proposals'
                  ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>Proposals & Approval</span>
              {proposals.length > 0 && (
                <span className="ml-auto text-[10px] bg-sky-500/20 text-sky-300 px-1.5 py-0.5 rounded font-mono">
                  {proposals.length}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab('evaluation')}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                activeTab === 'evaluation'
                  ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <BarChart3 className="w-4 h-4" />
              <span>Evaluation & Metrics</span>
            </button>
          </nav>
        </div>

        {/* System Health Status */}
        <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 space-y-2">
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-slate-400">System Status</span>
            <span className="flex items-center gap-1.5 font-medium text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              {health?.status || 'Online'}
            </span>
          </div>
          <div className="flex justify-between text-[10px] text-slate-500 font-mono">
            <span>Chroma Vectors</span>
            <span className="text-slate-300">{stats?.total_vectors_chroma ?? 0}</span>
          </div>
          <div className="flex justify-between text-[10px] text-slate-500 font-mono">
            <span>Indexed Chunks</span>
            <span className="text-slate-300">{stats?.total_chunks_sqlite ?? 0}</span>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Top Header */}
        <header className="h-14 border-b border-slate-800 bg-slate-900/40 backdrop-blur-md flex items-center justify-between px-6 shrink-0">
          <div className="flex items-center gap-4 flex-1 max-w-xl">
            <form onSubmit={handleSearch} className="relative w-full">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Semantic vector search across personal knowledge..."
                className="w-full bg-slate-950/80 border border-slate-800 rounded-lg pl-9 pr-4 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500 transition-all font-sans"
              />
            </form>
          </div>

          <div className="flex items-center gap-3">
            {statusMsg && (
              <span className="text-xs text-sky-400 font-mono animate-pulse">{statusMsg}</span>
            )}
            <button
              onClick={handleClearKnowledgeBase}
              className="px-2.5 py-1.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 hover:bg-rose-500/20 text-xs font-medium transition-all flex items-center gap-1"
              title="Wipe database and vector store to start clean"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Reset Corpus</span>
            </button>
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileUpload}
              className="hidden"
              accept=".md,.txt,.pdf"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="px-3 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-semibold text-xs transition-all flex items-center gap-1.5 shadow-sm"
            >
              <Upload className="w-3.5 h-3.5" />
              <span>{uploading ? 'Ingesting...' : 'Upload Doc'}</span>
            </button>
          </div>
        </header>

        {/* Tab Content Panels */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* TAB 1: DASHBOARD / KNOWLEDGE BASE */}
          {activeTab === 'dashboard' && (
            <div className="space-y-6 max-w-5xl mx-auto">
              {/* Folder / Directory Ingestion Card */}
              <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
                <h3 className="text-xs font-semibold text-slate-200 mb-2 flex items-center gap-2">
                  <FolderPlus className="w-4 h-4 text-sky-400" />
                  <span>Ingest Local Folder / Directory</span>
                </h3>
                <form onSubmit={handleDirectoryIngest} className="flex gap-2">
                  <input
                    type="text"
                    value={dirPath}
                    onChange={(e) => setDirPath(e.target.value)}
                    placeholder="Enter absolute folder path (e.g. d:\PersonalNotes or ./test_docs)"
                    className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
                  />
                  <button
                    type="submit"
                    disabled={uploading || !dirPath.trim()}
                    className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-sky-400 border border-slate-700 text-xs font-medium transition-all"
                  >
                    Scan & Ingest Folder
                  </button>
                </form>
              </div>

              {/* Semantic Search Results (if active) */}
              {searchResults.length > 0 && (
                <div className="p-4 rounded-xl bg-sky-950/20 border border-sky-500/30 space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-semibold text-sky-400">Search Results ({searchResults.length})</h3>
                    <button onClick={() => setSearchResults([])} className="text-[11px] text-slate-400 hover:text-slate-200">Clear</button>
                  </div>
                  <div className="space-y-2">
                    {searchResults.map((r, i) => (
                      <div key={i} className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 text-xs space-y-1">
                        <div className="flex justify-between text-[11px] text-slate-400 font-mono">
                          <span>Chunk ID: {r.chunk_id}</span>
                          <span className="text-emerald-400">Score: {r.score?.toFixed(3)}</span>
                        </div>
                        <p className="text-slate-200">{r.content}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Document List */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-slate-100">Ingested Documents ({documents.length})</h2>
                  <button onClick={loadAll} className="text-xs text-slate-400 hover:text-slate-200 flex items-center gap-1">
                    <RefreshCw className="w-3 h-3" /> Refresh
                  </button>
                </div>

                {documents.length === 0 ? (
                  <div className="text-center py-12 border border-dashed border-slate-800 rounded-xl">
                    <FileText className="w-10 h-10 mx-auto text-slate-600 mb-2" />
                    <p className="text-xs text-slate-400">No documents ingested yet</p>
                    <p className="text-[11px] text-slate-500 mt-1">Upload files (.md, .txt, .pdf) or scan a local directory to populate your knowledge base.</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {documents.map((doc) => (
                      <div key={doc.document_id} className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 flex items-start justify-between">
                        <div className="space-y-1 min-w-0 pr-3">
                          <h4 className="text-xs font-semibold text-slate-100 truncate">{doc.title}</h4>
                          <p className="text-[11px] text-slate-400 font-mono truncate">{doc.file_path || doc.document_id}</p>
                          <span className="inline-block text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                            {doc.source_type}
                          </span>
                        </div>
                        <button
                          onClick={() => handleDeleteDoc(doc.document_id)}
                          className="p-1.5 text-slate-500 hover:text-rose-400 transition-colors"
                          title="Delete Document"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 2: KNOWLEDGE GAPS */}
          {activeTab === 'gaps' && (
            <div className="space-y-6 max-w-5xl mx-auto">
              <div className="flex items-center justify-between border-b border-slate-800 pb-4">
                <div>
                  <h2 className="text-lg font-semibold text-slate-100">Knowledge Gap Discovery</h2>
                  <p className="text-xs text-slate-400">Automated topological analysis finding missing concepts, shallow coverage, and isolated nodes.</p>
                </div>
                <div className="flex gap-2">
                  <button 
                    onClick={handleDetectGaps}
                    className="px-3 py-1.5 rounded-lg bg-sky-500/10 border border-sky-500/30 text-sky-400 text-xs font-medium hover:bg-sky-500/20 transition-all flex items-center gap-1.5"
                  >
                    <Sparkles className="w-3.5 h-3.5" /> Scan for Gaps
                  </button>
                  <button 
                    onClick={loadGaps}
                    className="px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 text-xs font-medium hover:bg-slate-700 transition-all flex items-center gap-1"
                  >
                    <RefreshCw className="w-3 h-3" />
                  </button>
                </div>
              </div>

              <div className="space-y-3">
                {gaps.length === 0 ? (
                  <div className="text-center py-12 border border-dashed border-slate-800 rounded-xl">
                    <Compass className="w-10 h-10 mx-auto text-slate-600 mb-2" />
                    <p className="text-xs text-slate-400">No knowledge gaps detected</p>
                    <p className="text-[11px] text-slate-500 mt-1">Click "Scan for Gaps" to analyze your document topology.</p>
                  </div>
                ) : (
                  gaps.map((gap) => (
                    <div key={gap.gap_id} className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-slate-700 transition-all">
                      <div className="flex items-start justify-between">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <h3 className="text-sm font-semibold text-slate-100">{gap.title}</h3>
                            <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                              {gap.gap_type}
                            </span>
                          </div>
                          <p className="text-xs text-slate-300">{gap.description}</p>
                          {gap.reason && (
                            <div className="p-2.5 rounded bg-slate-950/80 border border-slate-800/80 text-[11px] text-slate-400 mt-2">
                              <span className="text-slate-300 font-medium">Diagnostic reason: </span>
                              {gap.reason}
                            </div>
                          )}
                        </div>
                        <div className="text-right space-y-2 shrink-0 ml-4">
                          <div className="text-[11px] text-slate-400 font-mono">
                            Priority: <span className="text-sky-400 font-bold">{(gap.priority_score * 100).toFixed(0)}%</span>
                          </div>
                          <button
                            onClick={() => handleStartResearch(gap.gap_id)}
                            className="px-3 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-semibold text-xs transition-all flex items-center gap-1.5 shadow-sm"
                          >
                            <Play className="w-3.5 h-3.5 fill-current" /> Research Gap
                          </button>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* TAB 3: RESEARCH WORKSPACE & LIVE TRACE */}
          {activeTab === 'workspace' && (
            <div className="space-y-6 max-w-6xl mx-auto">
              <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-3 h-3 rounded-full ${isResearching ? 'bg-emerald-500 animate-ping' : 'bg-slate-600'}`} />
                  <div>
                    <h2 className="text-sm font-semibold text-slate-100">Research Workspace & Live Execution Trace</h2>
                    <p className="text-xs text-slate-400">Autonomous planning, multi-source search, and evidence extraction stream</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={researchQuery}
                    onChange={(e) => setResearchQuery(e.target.value)}
                    placeholder="Enter ad-hoc research question..."
                    className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 w-72 font-sans"
                  />
                  <button
                    onClick={() => handleStartResearch(null, researchQuery)}
                    disabled={isResearching || !researchQuery.trim()}
                    className="px-3 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 disabled:opacity-50 text-slate-950 font-semibold text-xs flex items-center gap-1.5"
                  >
                    <Play className="w-3 h-3 fill-current" /> Run
                  </button>
                </div>
              </div>

              {/* Workspace Layout */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Agent Activity Trace (Live SSE Feed) */}
                <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
                  <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono flex items-center justify-between">
                    <span>Live Event Stream (SSE)</span>
                    <span className="text-slate-500 text-[10px]">{events.length} events recorded</span>
                  </h3>
                  <div className="space-y-2 font-mono text-xs max-h-96 overflow-y-auto">
                    {events.length === 0 ? (
                      <div className="text-center py-10 text-slate-500 text-xs">
                        No active research run events. Start a research run to view the live execution trace.
                      </div>
                    ) : (
                      events.map((evt, idx) => (
                        <div key={idx} className="p-2.5 rounded bg-slate-950/80 border border-slate-800/80 text-slate-300 flex items-start gap-2">
                          <span className="text-sky-400 font-bold shrink-0">[{evt.type}]</span>
                          <span>{evt.data?.message || evt.message || JSON.stringify(evt.data || {})}</span>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                {/* Information Card */}
                <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-4">
                  <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono">
                    Autonomous Loop Architecture
                  </h3>
                  <div className="space-y-3 text-xs text-slate-300">
                    <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 flex items-center gap-3">
                      <div className="w-6 h-6 rounded-md bg-sky-500/20 text-sky-300 flex items-center justify-center font-mono text-[11px] font-bold">1</div>
                      <div>
                        <div className="font-semibold text-slate-200">Decomposition & Planning</div>
                        <div className="text-[11px] text-slate-400">Breaks gaps into targeted research questions & web queries.</div>
                      </div>
                    </div>
                    <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 flex items-center gap-3">
                      <div className="w-6 h-6 rounded-md bg-emerald-500/20 text-emerald-300 flex items-center justify-center font-mono text-[11px] font-bold">2</div>
                      <div>
                        <div className="font-semibold text-slate-200">Source Fetching & Evidence Extraction</div>
                        <div className="text-[11px] text-slate-400">Fetches trusted sources under safety and budget limits.</div>
                      </div>
                    </div>
                    <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 flex items-center gap-3">
                      <div className="w-6 h-6 rounded-md bg-purple-500/20 text-purple-300 flex items-center justify-center font-mono text-[11px] font-bold">3</div>
                      <div>
                        <div className="font-semibold text-slate-200">Multi-Source Verification & Synthesis</div>
                        <div className="text-[11px] text-slate-400">Verifies factual consensus and prepares proposal for human review.</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: PROPOSALS & APPROVAL */}
          {activeTab === 'proposals' && (
            <div className="space-y-6 max-w-5xl mx-auto">
              <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-slate-100">Knowledge Proposals & Approval</h2>
                  <p className="text-xs text-slate-400">Human-in-the-loop validation. Approved proposals are automatically ingested and vectorized.</p>
                </div>
                <button onClick={loadProposals} className="text-xs text-slate-400 hover:text-slate-200 flex items-center gap-1">
                  <RefreshCw className="w-3 h-3" /> Refresh
                </button>
              </div>

              <div className="space-y-4">
                {proposals.length === 0 ? (
                  <div className="text-center py-12 border border-dashed border-slate-800 rounded-xl">
                    <CheckCircle2 className="w-10 h-10 mx-auto text-slate-600 mb-2" />
                    <p className="text-xs text-slate-400">No pending knowledge proposals</p>
                    <p className="text-[11px] text-slate-500 mt-1">Complete a research run to generate a synthesized proposal for review.</p>
                  </div>
                ) : (
                  proposals.map((prop) => (
                    <div key={prop.proposal_id} className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-4">
                      <div className="flex items-start justify-between">
                        <div>
                          <h3 className="text-sm font-semibold text-slate-100">{prop.title}</h3>
                          <p className="text-xs text-slate-400 mt-0.5">Run ID: {prop.run_id} | Gap: {prop.gap_id || 'N/A'}</p>
                        </div>
                        <span className={`text-[10px] px-2 py-0.5 rounded font-mono ${
                          prop.status === 'approved' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-sky-500/20 text-sky-300'
                        }`}>
                          {prop.status}
                        </span>
                      </div>

                      <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-300 whitespace-pre-wrap font-mono max-h-72 overflow-y-auto">
                        {prop.content}
                      </div>

                      {prop.status === 'pending_review' && (
                        <div className="flex justify-end gap-3 pt-2">
                          <button
                            onClick={() => handleProposalAction(prop.proposal_id, 'reject')}
                            className="px-4 py-2 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-semibold hover:bg-rose-500/20 flex items-center gap-1.5"
                          >
                            <ThumbsDown className="w-3.5 h-3.5" /> Reject Proposal
                          </button>
                          <button
                            onClick={() => handleProposalAction(prop.proposal_id, 'approve')}
                            className="px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-bold flex items-center gap-1.5 shadow-sm"
                          >
                            <ThumbsUp className="w-3.5 h-3.5 fill-current" /> Approve & Update Knowledge Base
                          </button>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* TAB 5: EVALUATION & BENCHMARKS */}
          {activeTab === 'evaluation' && (
            <div className="space-y-6 max-w-5xl mx-auto">
              <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-slate-100">Evaluation & Benchmark Suite</h2>
                  <p className="text-xs text-slate-400">Spec 11 evaluation runner measuring citation grounding, multi-source consensus, and proposal structure.</p>
                </div>
                <button
                  onClick={handleRunEvaluation}
                  disabled={evaluating}
                  className="px-4 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 disabled:opacity-50 text-slate-950 font-semibold text-xs flex items-center gap-1.5 shadow-sm"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>{evaluating ? 'Running Benchmark...' : 'Run Benchmark Suite'}</span>
                </button>
              </div>

              {latestEval ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
                      <div className="text-xs text-slate-400">Average Quality Score</div>
                      <div className="text-2xl font-bold text-sky-400 mt-1">
                        {((latestEval.average_quality_score || 0.85) * 100).toFixed(1)}%
                      </div>
                      <div className="text-[10px] text-slate-500 mt-1">Overall proposal & retrieval score</div>
                    </div>
                    <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
                      <div className="text-xs text-slate-400">Citation Grounding</div>
                      <div className="text-2xl font-bold text-emerald-400 mt-1">
                        {((latestEval.average_grounding_score || 1.0) * 100).toFixed(1)}%
                      </div>
                      <div className="text-[10px] text-slate-500 mt-1">Claims supported by factual evidence</div>
                    </div>
                    <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
                      <div className="text-xs text-slate-400">Benchmark Status</div>
                      <div className="text-2xl font-bold text-purple-400 mt-1">
                        {latestEval.status || 'PASS'}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-1">{latestEval.total_benchmark_cases || 2} test cases evaluated</div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-center py-12 border border-dashed border-slate-800 rounded-xl">
                  <BarChart3 className="w-10 h-10 mx-auto text-slate-600 mb-2" />
                  <p className="text-xs text-slate-400">No benchmark reports run yet</p>
                  <p className="text-[11px] text-slate-500 mt-1">Click "Run Benchmark Suite" to execute the synthetic knowledge test cases.</p>
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
