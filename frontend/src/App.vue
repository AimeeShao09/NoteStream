<script setup>
import { computed, reactive, ref } from 'vue'

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
  quizPdf: false
})

const errorMessage = ref('')
const summaryResult = ref(null)
const notesResult = ref(null)
const quizResult = ref(null)

const canGenerate = computed(() => Boolean(input.youtube_url && input.bailian_api_key))

function resolveUrl(path) {
  const base = apiBase.value.replace(/\/$/, '')
  return `${base}${path}`
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
    notesResult.value = null
    quizResult.value = null
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
  } catch (err) {
    errorMessage.value = err.message
  } finally {
    loading.notes = false
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
  <div class="min-h-screen bg-scene pb-12">
    <div class="mx-auto max-w-5xl px-4 pt-8 sm:px-6">
      <header class="glass-card animate-rise">
        <p class="font-mono text-xs tracking-[0.2em] text-blue-700">NOTESTREAM PWA</p>
        <h1 class="mt-2 font-display text-4xl font-bold text-slate-900">Turn YouTube Tutorials into Study Materials</h1>
        <p class="mt-3 max-w-2xl text-sm text-slate-700">
          Enter a YouTube URL and your Bailian API key, review the summary, then generate notes and quizzes with PDF export.
        </p>
      </header>

      <main class="mt-6 grid gap-6 lg:grid-cols-2">
        <section class="glass-card lg:col-span-2">
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="field">
              Backend API Base
              <input v-model="apiBase" placeholder="http://localhost:8000" />
            </label>
            <label class="field">
              Bailian Model
              <input v-model="input.model" placeholder="qwen3.5-plus" />
            </label>
            <label class="field sm:col-span-2">
              YouTube URL
              <input v-model="input.youtube_url" placeholder="https://www.youtube.com/watch?v=..." />
            </label>
            <label class="field sm:col-span-2">
              Bailian API Key
              <input v-model="input.bailian_api_key" type="password" placeholder="sk-..." />
            </label>
          </div>
          <div class="mt-4 flex flex-wrap items-center gap-3">
            <label class="inline-flex items-center gap-2 text-sm text-slate-700">
              <input v-model="input.force_refresh" type="checkbox" class="h-4 w-4" />
              Force refresh (skip cache)
            </label>
            <button class="btn" :disabled="!canGenerate || loading.summary" @click="requestSummary">
              {{ loading.summary ? 'Generating...' : '1) Generate Summary' }}
            </button>
          </div>
        </section>

        <section class="glass-card lg:col-span-2" v-if="errorMessage">
          <p class="text-sm font-semibold text-red-700">{{ errorMessage }}</p>
        </section>

        <section class="glass-card lg:col-span-2" v-if="summaryResult">
          <h2 class="section-title">Summary & Video Info</h2>
          <div class="mt-3 grid gap-4 sm:grid-cols-[150px_1fr]">
            <img
              v-if="summaryResult.video.thumbnail"
              :src="summaryResult.video.thumbnail"
              :alt="summaryResult.video.title"
              class="h-28 w-full rounded-xl object-cover"
            />
            <div class="space-y-2 text-sm">
              <p class="font-semibold text-slate-900">{{ summaryResult.video.title }}</p>
              <p class="text-slate-600">Channel: {{ summaryResult.video.channel }}</p>
              <p class="text-slate-600">Transcript words: {{ summaryResult.transcript_word_count }}</p>
              <p class="text-slate-600">Published: {{ summaryResult.video.publish_date || 'Unknown' }}</p>
            </div>
          </div>
          <article class="markdown-box mt-4">
            <p>{{ summaryResult.summary }}</p>
          </article>
        </section>

        <section class="glass-card" v-if="summaryResult">
          <h2 class="section-title">2) Generate Notes</h2>
          <div class="mt-3 grid gap-3">
            <label class="field">
              Note Style
              <select v-model="notesForm.note_style">
                <option value="cornell">Cornell</option>
                <option value="mind_map">Mind Map</option>
                <option value="hierarchical">Hierarchical</option>
                <option value="custom">Custom</option>
              </select>
            </label>
            <label class="field" v-if="notesForm.note_style === 'custom'">
              Custom Style Description
              <textarea v-model="notesForm.custom_style_description" rows="3" />
            </label>
          </div>
          <div class="mt-4 flex flex-wrap gap-2">
            <button class="btn" :disabled="loading.notes" @click="requestNotes">
              {{ loading.notes ? 'Generating...' : 'Generate Notes' }}
            </button>
            <button class="btn-secondary" :disabled="loading.notesPdf || !canGenerate" @click="downloadPdf('notes')">
              {{ loading.notesPdf ? 'Exporting...' : 'Download Notes PDF' }}
            </button>
          </div>
          <div
            class="mindmap-box mt-4"
            v-if="notesResult && notesForm.note_style === 'mind_map' && notesResult.mind_map_svg"
            v-html="notesResult.mind_map_svg"
          />
          <pre class="markdown-box mt-4" v-else-if="notesResult">{{ notesResult.content_markdown }}</pre>
        </section>

        <section class="glass-card" v-if="summaryResult">
          <h2 class="section-title">3) Generate Quiz</h2>
          <div class="mt-3 grid gap-3">
            <label class="field">
              Quiz Type
              <select v-model="quizForm.quiz_type">
                <option value="none">None</option>
                <option value="multiple_choice">Multiple Choice</option>
                <option value="written_answers">Written Answers</option>
                <option value="exam_style">Exam Style</option>
                <option value="custom">Custom</option>
              </select>
            </label>
            <label class="field">
              Difficulty
              <select v-model="quizForm.difficulty">
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
              </select>
            </label>
            <label class="field" v-if="quizForm.quiz_type === 'exam_style'">
              Exam Name
              <input v-model="quizForm.exam_name" placeholder="IELTS Writing Task 2" />
            </label>
            <label class="field" v-if="quizForm.quiz_type === 'custom'">
              Custom Quiz Description
              <textarea v-model="quizForm.custom_quiz_description" rows="3" />
            </label>
          </div>
          <div class="mt-4 flex flex-wrap gap-2">
            <button class="btn" :disabled="loading.quiz" @click="requestQuiz">
              {{ loading.quiz ? 'Generating...' : 'Generate Quiz' }}
            </button>
            <button class="btn-secondary" :disabled="loading.quizPdf || !canGenerate" @click="downloadPdf('quiz')">
              {{ loading.quizPdf ? 'Exporting...' : 'Download Quiz PDF' }}
            </button>
          </div>
          <pre class="markdown-box mt-4" v-if="quizResult">{{ quizResult.content_markdown }}</pre>
        </section>
      </main>
    </div>
  </div>
</template>
