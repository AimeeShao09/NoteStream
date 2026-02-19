from __future__ import annotations

from notestream.models import NoteStyle, QuizType

SUMMARY_PROMPT = """
You are an expert instructional analyst.

Write a neutral, informative summary (150-300 words) of this YouTube tutorial.
Purpose: help a learner decide whether the video is relevant and understand its high-level structure.

Constraints:
- Focus on the major topics and their sequence.
- Explain the teaching approach.
- Avoid granular implementation details.
- Write in third person.

Video title: {title}
Channel: {channel}
Transcript:
{transcript}
""".strip()

NOTE_PROMPTS = {
    NoteStyle.CORNELL: """
You are an expert study notes creator. Generate comprehensive Cornell-style notes from the transcript below.

Layout rules:
- Divide content into logical topic sections.
- For each section, produce TWO columns:
    LEFT - Cue Column: concise keywords, short questions, or memory triggers.
    RIGHT - Note-Taking Column: detailed explanations, facts, definitions, and information.
- At the bottom of each section, add a Summary block (2-4 sentences).

Content requirements:
- Vocabulary / Glossary: a dedicated end-section listing every technical term with a concise definition.
- Comparison tables: whenever the video contrasts >= 2 concepts, methods, or tools.
- Timelines / step lists: for any historical sequence, process, or workflow.
- Examples: reproduce ALL examples from the transcript. For any concept that lacks an example, generate one and label it [Generated Example].
- Formulas / code: include verbatim, formatted in a code block.
- Completeness: do NOT omit any concept, fact, or point from the video.

Output: Structured Markdown.

Video title: {title} | Channel: {channel}
Transcript: {transcript}
""".strip(),
    NoteStyle.MIND_MAP: """
You are an expert study notes creator. Generate a comprehensive mind map in nested Markdown outline format.

Structure:
- Central node: main topic of the video.
- Level 1 branches: major themes or sections (4-8 branches).
- Level 2 branches: key concepts, subtopics, or arguments.
- Level 3 branches: supporting details, examples, data points, definitions.
- Leaf nodes: concrete facts, formulas, examples, or memorable phrases.

Content requirements:
- Full coverage with no omission.
- Comparisons as parallel sibling branches under "Comparison: [Topic]".
- Generated examples must end with "(Generated Example)".
- Include a dedicated "Key Terms" branch with inline definitions.

Output: Nested Markdown list using ONLY list items (- item), no prose paragraphs.

Video title: {title} | Channel: {channel}
Transcript: {transcript}
""".strip(),
    NoteStyle.HIERARCHICAL: """
You are an expert study notes creator. Generate comprehensive hierarchical outline notes from the transcript below.

Structure:
1. Major Topic
   1.1 Sub-topic
      1.1.1 Supporting detail
         - Granular fact, example, or data point

Rules:
- Strict logical hierarchy.
- Vocabulary / Glossary: alphabetically sorted end-section with term definitions.
- Comparison tables: whenever >= 2 items are contrasted.
- Timelines / numbered step lists: for sequential processes or workflows.
- Examples: reproduce transcript examples; generate and label [Generated Example] where missing.
- Formulas / code snippets / equations: include verbatim in code blocks.
- Completeness: exhaustive coverage.

Output: Structured Markdown with numbered headings and nested bullet points.

Video title: {title} | Channel: {channel}
Transcript: {transcript}
""".strip(),
    NoteStyle.CUSTOM: """
You are an expert study notes creator. The user has requested their notes in this custom style:

"{custom_style_description}"

Use that style as formatting guidance, then generate comprehensive notes from the transcript.

Non-negotiable content requirements:
- Cover EVERY concept, fact, and point from the transcript.
- Vocabulary / Glossary with all technical terms.
- Comparison tables when >= 2 concepts are contrasted.
- Timelines / step lists for sequential processes.
- Examples: reproduce all transcript examples exactly; generate and label [Generated Example] where missing.
- Formulas / code: include verbatim in code blocks.

Output: Markdown structured according to the style description.

Video title: {title} | Channel: {channel}
Transcript: {transcript}
""".strip(),
}

QUIZ_PROMPTS = {
    QuizType.FLASHCARDS: """
You are an expert quiz creator. Generate flashcards testing knowledge of the video below.

Each flashcard:
FRONT: concise question OR vocabulary term.
BACK: answer, definition, or explanation (2-5 sentences max).

Difficulty rules (current difficulty: {difficulty}):
- easy: core introductory concepts.
- medium: all concepts from the video comprehensively.
- hard: scenario-based or application questions requiring transfer.

Additional rules:
- At least one flashcard per distinct concept.
- Vocabulary flashcards for every technical term.
- No duplicate questions.

Output Markdown:
**Card [N]**
FRONT: ...
BACK: ...

Video title: {title} | Channel: {channel}
Transcript: {transcript}
""".strip(),
    QuizType.MULTIPLE_CHOICE: """
You are an expert quiz creator. Generate a multiple-choice quiz from the transcript below.

Each question:
- Clear, unambiguous stem.
- Exactly 4 options labelled A, B, C, D.
- Exactly one correct answer.
- Plausible distractors.

Difficulty rules (current difficulty: {difficulty}):
- easy: foundational recall only.
- medium: comprehensive coverage.
- hard: reasoning, inference, and application.

Output Markdown:
Quiz section:
[N]. [Question stem]
A) ... B) ... C) ... D) ...

## Answer Key
[N]. Correct: [Letter] - [Explanation]. Distractors: ...

Video title: {title} | Channel: {channel}
Transcript: {transcript}
""".strip(),
    QuizType.WRITTEN_ANSWERS: """
You are an expert quiz creator. Generate an open-ended written-answer quiz.

Each question should:
- Require paragraph responses.
- Test understanding, not verbatim recall.
- Be answerable using video knowledge.

Difficulty rules (current difficulty: {difficulty}):
- easy: explain key concepts.
- medium: connect multiple ideas.
- hard: analysis/evaluation/application.

Output Markdown:
Quiz section: numbered list.

## Mark Scheme
For each question:
Model Answer: ...
Marking Criteria: bullet list.

Video title: {title} | Channel: {channel}
Transcript: {transcript}
""".strip(),
    QuizType.EXAM_STYLE: """
You are an expert exam paper creator. The student is preparing for: {exam_name}.

Step 1: retrieve official assessment objectives, question formats, mark allocation conventions, and rubrics for {exam_name}, then apply them.
Step 2: write a practice paper based on the transcript.

Requirements:
- Mirror structure and question types of real papers.
- Show marks per question.
- Include total marks and suggested time.
- Content should come from transcript at exam-appropriate level.

Difficulty (current: {difficulty}): easy foundational, medium standard, hard higher-order application.

Output Markdown:
Exam paper section.

## Mark Scheme
Examiner-style marking points and band descriptors.

Video title: {title} | Channel: {channel}
Transcript: {transcript}
""".strip(),
    QuizType.CROSSWORD: """
You are an expert puzzle designer. Generate a crossword puzzle testing vocabulary.

Steps:
1. Extract >=15 key terms from transcript.
2. Write precise clues (1-2 sentences).
3. Arrange terms into a valid crossword grid with ACROSS and DOWN coordinates.
4. Ensure all intersections match and no isolated words.

Output Markdown:
Puzzle section with ACROSS and DOWN clues and ASCII grid.

## Solution
Filled ASCII grid and answer list.

Video title: {title} | Channel: {channel}
Transcript: {transcript}
""".strip(),
    QuizType.CUSTOM: """
You are an expert quiz creator. The user wants this custom format:

"{custom_quiz_description}"

Generate a quiz from transcript following this format.

Difficulty rules (current: {difficulty}):
- easy: foundational concepts only
- medium: comprehensive coverage
- hard: inference, transfer, and flexible application

Rules:
- Every question must be unambiguously answerable from the video (or general knowledge for hard).
- Include separate Answer Key / Mark Scheme section.

Output Markdown matching the custom format.

Video title: {title} | Channel: {channel}
Transcript: {transcript}
""".strip(),
}
