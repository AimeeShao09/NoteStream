<script setup>
import { computed, reactive, ref } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'

const apiBase = ref(import.meta.env.VITE_API_BASE || 'http://localhost:8000')

const input = reactive({
  youtube_url: '',
  bailian_api_key: '',
  model: 'qwen3.5-plus',
  force_refresh: false
})

const notesForm = reactive({
  note_style: 'hierarchical',
  custom_style_description: ''
})

const quizForm = reactive({
  quiz_type: 'multiple_choice',
  difficulty: 'medium',
  exam_name: '',
  custom_quiz_description: ''
})

const loading = reactive({
  summary: false,
  notes: false,
  quiz: false,
  notesPdf: false,
  quizPdf: false,
  notesChat: false
})

const errorMessage = ref('')
const activePanel = ref('summary')
const summaryResult = ref(null)
const notesResult = ref(null)
const quizResult = ref(null)
const notesChatMessages = ref([])
const notesChatInput = ref('')
const notesChatSettings = reactive({
  exam_mode: false,
  exam_name: ''
})

const canGenerate = computed(() => Boolean(input.youtube_url && input.bailian_api_key))
const renderedNotesMarkdown = computed(() => {
  const source = notesResult.value?.content_markdown || ''
  const prepared = notesForm.note_style === 'hierarchical' ? normalizeHierarchicalMarkdown(source) : source
  return renderMarkdown(prepared)
})
const renderedQuizMarkdown = computed(() => renderMarkdown(quizResult.value?.content_markdown || ''))
const canAskNotes = computed(
  () =>
    Boolean(
      notesResult.value?.content_markdown &&
        input.bailian_api_key &&
        notesChatInput.value.trim() &&
        (!notesChatSettings.exam_mode || notesChatSettings.exam_name.trim())
    )
)

marked.setOptions({
  gfm: true,
  breaks: true
})

function resolveUrl(path) {
  const base = apiBase.value.replace(/\/$/, '')
  return `${base}${path}`
}

function renderMarkdown(markdown) {
  const raw = marked.parse(markdown || '')
  const sanitized = DOMPurify.sanitize(raw)
  const doc = new DOMParser().parseFromString(`<div id="md-root">${sanitized}</div>`, 'text/html')
  const root = doc.getElementById('md-root')
  if (!root) {
    return sanitized
  }

  root.querySelectorAll('pre').forEach((pre) => {
    if (!pre.textContent?.trim()) {
      pre.remove()
    }
  })

  return root.innerHTML
}

function normalizeHierarchicalMarkdown(markdown) {
  const lines = (markdown || '').split('\n')
  const normalized = []
  let currentSectionLevel = 1
  let inCodeFence = false

  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed.startsWith('```')) {
      inCodeFence = !inCodeFence
      normalized.push(line)
      continue
    }
    if (inCodeFence || !trimmed) {
      normalized.push(line)
      continue
    }
    if (trimmed.startsWith('|')) {
      normalized.push(line)
      continue
    }

    const numbered = trimmed.match(/^(\d+(?:\.\d+)*)(?:\.)?\s+(.+)$/)
    if (numbered) {
      const numbering = numbered[1]
      const title = numbered[2]
      const sectionLevel = numbering.split('.').filter(Boolean).length
      currentSectionLevel = Math.max(1, sectionLevel)
      normalized.push(`${'  '.repeat(currentSectionLevel - 1)}- **${numbering} ${title}**`)
      continue
    }

    const bullet = trimmed.match(/^-\s+(.+)$/)
    if (bullet) {
      normalized.push(`${'  '.repeat(currentSectionLevel)}- ${bullet[1]}`)
      continue
    }

    normalized.push(`${'  '.repeat(currentSectionLevel)}- ${trimmed}`)
  }

  return normalized.join('\n')
}

async function postJson(path, body) {
  const response = await fetch(resolveUrl(path), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(body)
  })

  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const payload = await response.json()
      detail = payload.detail || detail
    } catch {
      // ignore parse error
    }
    throw new Error(detail)
  }

  return response.json()
}

async function requestSummary() {
  errorMessage.value = ''
  loading.summary = true
  try {
    summaryResult.value = await postJson('/api/summary', {
      youtube_url: input.youtube_url,
      bailian_api_key: input.bailian_api_key,
      model: input.model,
      force_refresh: input.force_refresh
    })
  } catch (err) {
    errorMessage.value = err.message
  } finally {
    loading.summary = false
  }
}

async function requestNotes() {
  errorMessage.value = ''
  loading.notes = true
  try {
    notesResult.value = await postJson('/api/notes', {
      youtube_url: input.youtube_url,
      bailian_api_key: input.bailian_api_key,
      model: input.model,
      force_refresh: input.force_refresh,
      note_style: notesForm.note_style,
      custom_style_description: notesForm.custom_style_description || null
    })
    notesChatMessages.value = []
    notesChatInput.value = ''
  } catch (err) {
    errorMessage.value = err.message
  } finally {
    loading.notes = false
  }
}

async function askNotesAssistant() {
  const question = notesChatInput.value.trim()
  if (!question || !notesResult.value?.content_markdown) {
    return
  }
  if (notesChatSettings.exam_mode && !notesChatSettings.exam_name.trim()) {
    errorMessage.value = 'Please enter the exam or competition name when Exam Mode is enabled.'
    return
  }

  errorMessage.value = ''
  loading.notesChat = true

  const history = notesChatMessages.value
    .slice(-12)
    .map((message) => ({ role: message.role, content: message.content }))

  notesChatMessages.value.push({ role: 'user', content: question })
  notesChatInput.value = ''

  try {
    const response = await postJson('/api/notes/chat', {
      bailian_api_key: input.bailian_api_key,
      model: input.model,
      notes_markdown: notesResult.value.content_markdown,
      question,
      history,
      exam_mode: notesChatSettings.exam_mode,
      exam_name: notesChatSettings.exam_mode ? notesChatSettings.exam_name.trim() : null
    })
    notesChatMessages.value.push({ role: 'assistant', content: response.answer })
  } catch (err) {
    const detail = err?.message || 'Notes chat request failed.'
    if (detail === 'Not Found' || detail.includes('(404)')) {
      errorMessage.value = 'Notes chat API is unavailable. Please restart backend with the latest code.'
    } else {
      errorMessage.value = detail
    }
  } finally {
    loading.notesChat = false
  }
}

async function requestQuiz() {
  errorMessage.value = ''
  loading.quiz = true
  try {
    quizResult.value = await postJson('/api/quiz', {
      youtube_url: input.youtube_url,
      bailian_api_key: input.bailian_api_key,
      model: input.model,
      force_refresh: input.force_refresh,
      quiz_type: quizForm.quiz_type,
      difficulty: quizForm.difficulty,
      exam_name: quizForm.exam_name || null,
      custom_quiz_description: quizForm.custom_quiz_description || null
    })
  } catch (err) {
    errorMessage.value = err.message
  } finally {
    loading.quiz = false
  }
}

async function downloadPdf(type) {
  errorMessage.value = ''
  const isNotes = type === 'notes'
  loading[isNotes ? 'notesPdf' : 'quizPdf'] = true

  const payload = isNotes
    ? {
        youtube_url: input.youtube_url,
        bailian_api_key: input.bailian_api_key,
        model: input.model,
        force_refresh: input.force_refresh,
        note_style: notesForm.note_style,
        custom_style_description: notesForm.custom_style_description || null
      }
    : {
        youtube_url: input.youtube_url,
        bailian_api_key: input.bailian_api_key,
        model: input.model,
        force_refresh: input.force_refresh,
        quiz_type: quizForm.quiz_type,
        difficulty: quizForm.difficulty,
        exam_name: quizForm.exam_name || null,
        custom_quiz_description: quizForm.custom_quiz_description || null
      }

  try {
    const response = await fetch(resolveUrl(isNotes ? '/api/notes/pdf' : '/api/quiz/pdf'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })

    if (!response.ok) {
      let detail = `PDF download failed (${response.status})`
      try {
        const body = await response.json()
        detail = body.detail || detail
      } catch {
        // ignore parse error
      }
      throw new Error(detail)
    }

    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = isNotes ? 'notes.pdf' : 'quiz.pdf'
    link.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    errorMessage.value = err.message
  } finally {
    loading[isNotes ? 'notesPdf' : 'quizPdf'] = false
  }
}
</script>

<template>
  <div class="app-shell">
    <main class="workspace-sheet sketch-board">
      <header class="title-strip sketch-box">
        <div class="title-main">
          <svg class="workspace-icon" viewBox="0 0 48 48" aria-hidden="true">
            <rect x="2" y="4" width="44" height="40" rx="8" fill="#fff7ed" stroke="#0f172a" stroke-width="2" />
            <rect x="5" y="4" width="7" height="40" rx="3" fill="#fde68a" stroke="#0f172a" stroke-width="2" />
            <rect x="14" y="11" width="15" height="11" rx="2.5" fill="#fef3c7" stroke="#0f172a" stroke-width="1.6" />
            <path d="M20 14.2 L20 18.8 L24.2 16.5 Z" fill="#0f172a" />
            <line x1="14" y1="28" x2="38" y2="28" stroke="#334155" stroke-width="1.8" stroke-linecap="round" />
            <line x1="14" y1="33" x2="38" y2="33" stroke="#334155" stroke-width="1.8" stroke-linecap="round" />
            <line x1="14" y1="38" x2="31" y2="38" stroke="#334155" stroke-width="1.8" stroke-linecap="round" />
          </svg>
          <h1>Notestream Workspace</h1>
        </div>
      </header>

      <section class="input-grid sketch-box">
        <label class="input-row input-table-row">
          <span class="input-key input-table-key">URL</span>
          <input v-model="input.youtube_url" placeholder="https://www.youtube.com/watch?v=..." />
        </label>
        <label class="input-row input-table-row">
          <span class="input-key input-table-key">Key</span>
          <input v-model="input.bailian_api_key" type="password" placeholder="Bailian API key" />
        </label>
      </section>

      <details class="advanced-box sketch-box">
        <summary>Advanced Settings</summary>
        <div class="advanced-grid">
          <label>
            Backend API
            <input v-model="apiBase" placeholder="http://localhost:8000" />
          </label>
          <label>
            Model
            <input v-model="input.model" placeholder="qwen3.5-plus" />
          </label>
          <label class="checkbox-row">
            <input v-model="input.force_refresh" type="checkbox" />
            Force refresh (skip cache)
          </label>
        </div>
      </details>

      <nav class="panel-tabs action-tabs">
        <button :class="{ active: activePanel === 'summary' }" @click="activePanel = 'summary'">Summary</button>
        <button :class="{ active: activePanel === 'notes' }" @click="activePanel = 'notes'">Notes</button>
        <button :class="{ active: activePanel === 'quiz' }" @click="activePanel = 'quiz'">Quiz</button>
      </nav>

      <section class="panel-controls sketch-box" v-if="activePanel === 'summary'">
        <button class="action-btn" :disabled="!canGenerate || loading.summary" @click="requestSummary">
          {{ loading.summary ? 'Generating...' : 'Generate Summary' }}
        </button>
      </section>

      <section class="panel-controls sketch-box" v-else-if="activePanel === 'notes'">
        <label>
          Note Style
          <select v-model="notesForm.note_style">
            <option value="cornell">Cornell</option>
            <option value="mind_map">Mind Map</option>
            <option value="hierarchical">Hierarchical</option>
            <option value="custom">Custom</option>
          </select>
        </label>
        <label v-if="notesForm.note_style === 'custom'">
          Custom Description
          <input v-model="notesForm.custom_style_description" placeholder="e.g., Q&A style" />
        </label>
        <button class="action-btn" :disabled="!canGenerate || loading.notes" @click="requestNotes">
          {{ loading.notes ? 'Generating...' : 'Generate Notes' }}
        </button>
        <button class="sub-btn" :disabled="!notesResult || !canGenerate || loading.notesPdf" @click="downloadPdf('notes')">
          {{ loading.notesPdf ? 'Exporting...' : 'Download Notes PDF' }}
        </button>
      </section>

      <section class="panel-controls sketch-box" v-else>
        <label>
          Quiz Type
          <select v-model="quizForm.quiz_type">
            <option value="none">None</option>
            <option value="multiple_choice">Multiple Choice</option>
            <option value="written_answers">Written Answers</option>
            <option value="exam_style">Exam Style</option>
            <option value="custom">Custom</option>
          </select>
        </label>
        <label>
          Difficulty
          <select v-model="quizForm.difficulty">
            <option value="easy">Easy</option>
            <option value="medium">Medium</option>
            <option value="hard">Hard</option>
          </select>
        </label>
        <label v-if="quizForm.quiz_type === 'exam_style'">
          Exam Name
          <input v-model="quizForm.exam_name" placeholder="IELTS Writing Task 2" />
        </label>
        <label v-if="quizForm.quiz_type === 'custom'">
          Custom Description
          <input v-model="quizForm.custom_quiz_description" placeholder="e.g., fill in the blanks" />
        </label>
        <button class="action-btn" :disabled="!canGenerate || loading.quiz" @click="requestQuiz">
          {{ loading.quiz ? 'Generating...' : 'Generate Quiz' }}
        </button>
        <button class="sub-btn" :disabled="!quizResult || !canGenerate || loading.quizPdf" @click="downloadPdf('quiz')">
          {{ loading.quizPdf ? 'Exporting...' : 'Download Quiz PDF' }}
        </button>
      </section>

      <p class="error-line" v-if="errorMessage">{{ errorMessage }}</p>

      <section class="result-canvas sketch-box" :class="`result-${activePanel}`">
        <template v-if="activePanel === 'summary'">
          <div v-if="summaryResult" class="result-stack">
            <h2 class="result-title">{{ summaryResult.video.title }}</h2>
            <p class="meta-line">
              {{ summaryResult.video.channel }} | {{ summaryResult.transcript_word_count }} words |
              {{ summaryResult.video.publish_date || 'Unknown date' }}
            </p>
            <p class="result-text">{{ summaryResult.summary }}</p>
          </div>
          <p v-else class="empty-tip">Your summary will appear here.</p>
        </template>

        <template v-else-if="activePanel === 'notes'">
          <div class="notes-layout">
            <div class="notes-pane">
              <div v-if="notesResult && notesForm.note_style === 'mind_map' && notesResult.mind_map_svg" class="mindmap-wrap" v-html="notesResult.mind_map_svg" />
              <article v-else-if="notesResult" class="markdown-body" v-html="renderedNotesMarkdown" />
              <p v-else class="empty-tip">Your notes will appear here.</p>
            </div>

            <aside class="chat-pane">
              <h3 class="chat-title">Ask AI About Notes</h3>
              <div class="chat-mode-box">
                <label class="chat-mode-row">
                  <input v-model="notesChatSettings.exam_mode" type="checkbox" />
                  Exam Mode
                </label>
                <input
                  v-if="notesChatSettings.exam_mode"
                  v-model="notesChatSettings.exam_name"
                  class="chat-mode-input"
                  placeholder="Exam or competition name (e.g., AP Physics C, USACO)"
                />
              </div>

              <div class="chat-thread">
                <template v-if="notesChatMessages.length">
                  <div v-for="(message, index) in notesChatMessages" :key="index" class="chat-msg" :class="`chat-${message.role}`">
                    <p class="chat-role">{{ message.role === 'user' ? 'You' : 'AI Tutor' }}</p>
                    <article class="chat-md" v-html="renderMarkdown(message.content)" />
                  </div>
                </template>
                <p v-else class="empty-tip">
                  Ask a question like: “Summarize section 3 in simpler words.”
                </p>
              </div>

              <div class="chat-input-wrap">
                <textarea
                  v-model="notesChatInput"
                  rows="3"
                  placeholder="Ask about the notes..."
                  :disabled="!notesResult || loading.notesChat"
                  @keydown.enter.exact.prevent="askNotesAssistant"
                />
                <button class="action-btn" :disabled="!canAskNotes || loading.notesChat" @click="askNotesAssistant">
                  {{ loading.notesChat ? 'Thinking...' : 'Send' }}
                </button>
              </div>
            </aside>
          </div>
        </template>

        <template v-else>
          <article v-if="quizResult" class="markdown-body" v-html="renderedQuizMarkdown" />
          <p v-else class="empty-tip">Your quiz will appear here.</p>
        </template>
      </section>

      <footer class="page-credit">designed by tianyi shao</footer>
    </main>
  </div>
</template>
