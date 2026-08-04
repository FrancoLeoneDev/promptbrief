import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Finding } from '../core/models';
import { GeneratePage } from './generate-page';

function finding(over: Partial<Finding>): Finding {
  return {
    rule_id: 'r',
    family: 'completeness',
    severity: 'warning',
    message: 'falta algo',
    suggestion: 'poné algo',
    slot_name: null,
    ...over,
  };
}

const MISSING_SUCCESS = finding({
  rule_id: 'missing_success_criteria',
  severity: 'error',
  message: 'No declaraste cuándo la tarea está terminada.',
  suggestion: 'Agregá qué tiene que pasar para considerarla lista.',
  slot_name: 'success_criteria',
});

const MISSING_FILES = finding({
  rule_id: 'missing_file_scope',
  message: 'No hay ningún archivo en el alcance.',
  suggestion: 'Nombrá por dónde empezar.',
  slot_name: 'file_scope',
});

const VAGUE_TEXT = finding({
  rule_id: 'vague_wording',
  family: 'text',
  message: 'El pedido dice "mejorar" y no dice qué.',
  suggestion: 'Reemplazalo por algo medible.',
  slot_name: null,
});

describe('GeneratePage', () => {
  let fixture: ComponentFixture<GeneratePage>;
  let http: HttpTestingController;
  let page: HTMLElement;

  async function type(selector: string, value: string): Promise<void> {
    const field = page.querySelector(selector) as HTMLInputElement | HTMLTextAreaElement;
    field.value = value;
    field.dispatchEvent(new Event('input'));
    await fixture.whenStable();
  }

  async function click(label: string): Promise<void> {
    const button = [...page.querySelectorAll('button')].find((each) =>
      each.textContent?.includes(label),
    );
    button!.click();
    await fixture.whenStable();
  }

  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    fixture = TestBed.createComponent(GeneratePage);
    http = TestBed.inject(HttpTestingController);
    page = fixture.nativeElement as HTMLElement;

    await fixture.whenStable();
    http.expectOne('/api/profiles').flush([]);
    await fixture.whenStable();
  });

  afterEach(() => http.verify());

  async function analyze(findings: Finding[]): Promise<void> {
    await type('#task-text', 'arreglar el export de CSV');
    await click('Analizar');
    http.expectOne('/api/lint').flush({ task_type: 'code_change', findings });
    await fixture.whenStable();
  }

  it('arma un campo por cada hallazgo que nombra un slot', async () => {
    await analyze([MISSING_SUCCESS, MISSING_FILES, VAGUE_TEXT]);

    const questions = page.querySelectorAll('.question');
    expect(questions.length).toBe(2);
    expect(questions[0].textContent).toContain(MISSING_SUCCESS.message);
    expect(questions[0].textContent).toContain(MISSING_SUCCESS.suggestion);
  });

  it('deja los hallazgos sin slot como avisos, sin campo', async () => {
    await analyze([VAGUE_TEXT]);

    expect(page.querySelectorAll('.question').length).toBe(0);
    expect(page.querySelector('.remarks')?.textContent).toContain(VAGUE_TEXT.message);
  });

  it('muestra el tipo de tarea que detectó el servidor', async () => {
    await analyze([]);

    expect(page.textContent).toContain('cambio de código');
  });

  it('da varias filas a los campos de lista y una sola caja al resto', async () => {
    await analyze([MISSING_SUCCESS, MISSING_FILES]);

    expect(page.querySelector('#q-success_criteria')?.tagName).toBe('TEXTAREA');
    expect(page.querySelector('#q-file_scope')?.tagName).toBe('INPUT');

    await click('Agregar otro');
    expect(page.querySelectorAll('.row-item').length).toBe(2);
  });

  it('manda cada respuesta bajo el nombre de slot que mandó el servidor', async () => {
    // Es todo el truco: la clave del hallazgo es la clave del pedido, sin traducción.
    await analyze([MISSING_SUCCESS, MISSING_FILES]);

    await type('#q-success_criteria', 'que el CSV traiga las filas');
    await type('#q-file_scope', 'src/export.ts');
    await click('Generar brief');

    const request = http.expectOne('/api/brief');
    expect(request.request.body).toEqual({
      text: 'arreglar el export de CSV',
      success_criteria: 'que el CSV traiga las filas',
      file_scope: ['src/export.ts'],
    });
    request.flush({
      text: '<brief/>',
      task_type: 'code_change',
      findings: [],
      dropped_slots: [],
      selection: { selected: [], over_budget: [], not_applicable: [], skipped_for_review: [] },
    });
    await fixture.whenStable();

    expect(page.querySelector('.brief')?.textContent).toBe('<brief/>');
  });

  it('conserva el campo contestado aunque el hallazgo ya no vuelva', async () => {
    // El hallazgo desaparece justamente porque se contestó: si el campo se fuera con él,
    // el valor cargado quedaría invisible y sin forma de corregirlo.
    await analyze([MISSING_SUCCESS]);
    await type('#q-success_criteria', 'que el CSV traiga las filas');
    await click('Generar brief');

    http.expectOne('/api/brief').flush({
      text: '<brief/>',
      task_type: 'code_change',
      findings: [],
      dropped_slots: [],
      selection: { selected: [], over_budget: [], not_applicable: [], skipped_for_review: [] },
    });
    await fixture.whenStable();

    const question = page.querySelector('.question');
    expect(question).not.toBeNull();
    expect(question!.classList).toContain('answered');
    expect((page.querySelector('#q-success_criteria') as HTMLTextAreaElement).value).toBe(
      'que el CSV traiga las filas',
    );
  });
});
