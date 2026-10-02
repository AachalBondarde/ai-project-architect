import React, { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'

mermaid.initialize({ startOnLoad: false })

const TABS = ['overview', 'requirements', 'architecture', 'tech_stack', 'database', 'api', 'diagrams', 'security', 'reviewer', 'roadmap']

function Mermaid({ code }) {
  const root = useRef(null)
  useEffect(() => {
    mermaid.render(`diagram-${Math.random().toString(36).slice(2)}`, code)
      .then(result => { if (root.current) root.current.innerHTML = result.svg })
      .catch(error => { if (root.current) root.current.textContent = String(error) })
  }, [code])
  return <div ref={root} />
}

async function request(url, options) {
  const response = await fetch(url, options)
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || `Request failed (${response.status})`)
  }
  return response.json()
}

export default function App() {
  const [idea, setIdea] = useState('')
  const [users, setUsers] = useState(5000)
  const [budget, setBudget] = useState('Low')
  const [timeline, setTimeline] = useState('3 months')
  const [projects, setProjects] = useState([])
  const [log, setLog] = useState([])
  const [blueprint, setBlueprint] = useState(null)
  const [tab, setTab] = useState(TABS[0])
  const [projectId, setProjectId] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const refreshProjects = async () => {
    const savedProjects = await request('/api/projects')
    setProjects(savedProjects)
    return savedProjects
  }

  const watch = id => {
    setProjectId(id)
    setLog([])
    setBlueprint(null)
    setBusy(true)
    const events = new EventSource(`/api/projects/${id}/events`)
    events.onmessage = async message => {
      const event = JSON.parse(message.data)
      setLog(current => [...current, `${event.event}: ${event.agent || event.message || ''}`])
      if (event.event === 'complete') {
        events.close()
        try {
          setBlueprint(await request(`/api/projects/${id}/blueprint`))
          await refreshProjects()
        } catch (requestError) {
          setError(requestError.message)
        }
        setBusy(false)
      } else if (event.event === 'error') {
        events.close()
        setError(event.message || 'Project analysis failed.')
        setBusy(false)
        await refreshProjects()
      }
    }
    events.onerror = () => {
      events.close()
      setBusy(false)
      refreshProjects().catch(requestError => setError(requestError.message))
    }
  }

  const openProject = async id => {
    try {
      setError('')
      const project = await request(`/api/projects/${id}`)
      setProjectId(id)
      setIdea(project.idea)
      setUsers(project.users)
      setBudget(project.budget)
      setTimeline(project.timeline)
      setBlueprint(project.blueprint)
      setLog([])
      if (project.status === 'running') watch(id)
      else setBusy(false)
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  useEffect(() => {
    refreshProjects()
      .then(savedProjects => { if (savedProjects[0]) openProject(savedProjects[0].id) })
      .catch(requestError => setError(requestError.message))
  }, [])

  const createAndAnalyze = async () => {
    try {
      setError('')
      const project = await request('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idea, users, budget, timeline }),
      })
      await request(`/api/projects/${project.id}/analyze`, { method: 'POST' })
      await refreshProjects()
      watch(project.id)
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  const loadDemo = async () => {
    try {
      setError('')
      const project = await request('/api/projects/demo', { method: 'POST' })
      await refreshProjects()
      watch(project.id)
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  const section = blueprint?.[tab]

  return <main style={{ fontFamily: 'system-ui', maxWidth: 1080, margin: '0 auto', padding: 24 }}>
    <header>
      <h1>AI Project Architect</h1>
      <p>Turn a product idea into a reviewed, implementation-ready project blueprint.</p>
    </header>

    <section aria-label="Project requirements">
      <h2>Project requirements</h2>
      <textarea rows={4} style={{ width: '100%', boxSizing: 'border-box' }} placeholder="Describe your project idea" value={idea} onChange={event => setIdea(event.target.value)} />
      <p>
        Expected users <input type="number" min="1" value={users} onChange={event => setUsers(Number(event.target.value))} />{' '}
        Budget <select value={budget} onChange={event => setBudget(event.target.value)}><option>Low</option><option>Medium</option><option>High</option></select>{' '}
        Timeline <input value={timeline} onChange={event => setTimeline(event.target.value)} />{' '}
        <button onClick={createAndAnalyze} disabled={!idea.trim() || busy}>Analyze Project</button>{' '}
        <button onClick={loadDemo} disabled={busy}>Load Demo</button>
      </p>
    </section>

    <section aria-label="Saved projects">
      <h2>Projects</h2>
      {projects.length === 0 ? <p>No saved projects yet.</p> : <ul>
        {projects.map(project => <li key={project.id}>
          <button onClick={() => openProject(project.id)}>{project.idea.slice(0, 90)} ({project.status})</button>
        </li>)}
      </ul>}
    </section>

    {error && <p role="alert" style={{ color: '#a32121' }}>{error}</p>}
    {log.length > 0 && <section aria-label="Agent workflow">
      <h2>Agent workflow</h2>
      <pre style={{ background: '#171b1c', color: '#a8e6c1', padding: 12, maxHeight: 200, overflow: 'auto' }}>{log.join('\n')}</pre>
    </section>}

    {blueprint && <section aria-label="Project blueprint">
      <h2>Final Project Blueprint</h2>
      <nav aria-label="Blueprint sections">
        {TABS.map(sectionName => <button key={sectionName} onClick={() => setTab(sectionName)} aria-current={tab === sectionName ? 'page' : undefined}>
          {sectionName.replace('_', ' ')}
        </button>)}{' '}
        <a href={`/api/projects/${projectId}/export?format=markdown`} download>Export Markdown</a>{' '}
        <a href={`/api/projects/${projectId}/export?format=json`} target="_blank" rel="noreferrer">Export JSON</a>
      </nav>
      {tab === 'overview' && blueprint
        ? <div><h3>{blueprint.idea}</h3><p>{blueprint.architecture?.recommended}</p><p>{blueprint.architecture?.rationale}</p></div>
        : tab === 'diagrams' && section
        ? Object.entries(section).map(([name, code]) => <div key={name}><h3>{name}</h3><Mermaid code={code} /></div>)
        : <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(section, null, 2)}</pre>}
    </section>}
  </main>
}