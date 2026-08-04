/**
 * El contrato de la API, transcripto de `src/promptbrief/server/schemas.py`.
 *
 * Es una transcripción y no una generación automática porque la superficie es chica y
 * estable; lo que no se hace acá es *interpretar* nada del backend. En particular no
 * existe ningún mapeo de `rule_id` a campo del formulario: eso viaja en `slot_name`.
 */

export type TaskType = 'code_change' | 'debug' | 'writing';

export type SlotKind =
  'stack' | 'convention' | 'constraint' | 'glossary' | 'architecture' | 'unclassified';

export type Severity = 'error' | 'warning' | 'info';

export type Family = 'text' | 'completeness' | 'context';

export interface Provenance {
  file: string;
  line: number;
}

export interface Slot {
  id: string;
  kind: SlotKind;
  content: string;
  /** Vacío significa "aplica a todos los tipos de tarea", no "a ninguno". */
  applies_to: TaskType[];
  source: Provenance | null;
  needs_review: boolean;
  redacted: boolean;
}

export interface SourceFile {
  path: string;
  sha256: string;
}

export interface Profile {
  name: string;
  root: string;
  budget_tokens: number;
  sources: SourceFile[];
  slots: Slot[];
}

export interface ProfileSummary {
  name: string;
  slot_count: number;
  source_count: number;
}

export interface SlotChange {
  before: Slot;
  after: Slot;
}

export interface ProfileDiff {
  added: Slot[];
  removed: Slot[];
  modified: SlotChange[];
  unchanged: Slot[];
}

export interface Finding {
  rule_id: string;
  family: Family;
  severity: Severity;
  message: string;
  suggestion: string;
  /** El campo que le falta al pedido, o `null` si el defecto está en el texto. */
  slot_name: string | null;
}

export interface Selection {
  selected: Slot[];
  over_budget: Slot[];
  not_applicable: Slot[];
  skipped_for_review: Slot[];
}

export interface ScanRequest {
  root: string;
  name?: string | null;
  force?: boolean;
}

/**
 * El cuerpo de `/api/lint` y `/api/brief`.
 *
 * Los campos que el interrogatorio completa se escriben por índice —el `slot_name` del
 * hallazgo es la clave— así que la firma los deja abiertos a propósito: una regla nueva
 * en el backend estrena su campo sin tocar el front.
 */
export interface BriefRequest {
  text: string;
  task_type?: TaskType | null;
  profile_name?: string | null;
  success_criteria?: string | null;
  output_format?: string | null;
  file_scope?: string[];
  constraints?: string[];
  examples?: string[];
  repro_steps?: string | null;
  expected_vs_actual?: string | null;
  [slot: string]: unknown;
}

export interface LintResult {
  task_type: TaskType;
  findings: Finding[];
}

export interface BriefResult {
  text: string;
  task_type: TaskType;
  findings: Finding[];
  dropped_slots: string[];
  selection: Selection;
}

export const SLOT_KINDS: readonly SlotKind[] = [
  'stack',
  'convention',
  'constraint',
  'glossary',
  'architecture',
  'unclassified',
];

export const TASK_TYPES: readonly TaskType[] = ['code_change', 'debug', 'writing'];

/**
 * Los campos del pedido que aceptan varios valores.
 *
 * Es forma del cuerpo del pedido, no conocimiento de las reglas: `constraints` es una
 * lista en `BriefRequestBody` y lo va a seguir siendo. Un `slot_name` que no esté acá se
 * dibuja como campo de texto, así que una regla nueva no rompe el formulario.
 */
const LIST_SLOTS: ReadonlySet<string> = new Set(['file_scope', 'constraints', 'examples']);

export function isListSlot(slot: string): boolean {
  return LIST_SLOTS.has(slot);
}

const TASK_TYPE_LABELS: Record<TaskType, string> = {
  code_change: 'cambio de código',
  debug: 'depuración',
  writing: 'escritura',
};

export function taskTypeLabel(task: TaskType): string {
  return TASK_TYPE_LABELS[task] ?? task;
}

/** Cómo nombrar un slot ante el usuario: la procedencia si la hay, si no el id. */
export function slotLabel(slot: Slot): string {
  return slot.source ? `${slot.source.file}:${slot.source.line}` : slot.id;
}

/** "1 dato" / "10 datos". Los contadores de esta app son todos de una cifra o dos. */
export function counted(total: number, one: string, many: string): string {
  return `${total} ${total === 1 ? one : many}`;
}
