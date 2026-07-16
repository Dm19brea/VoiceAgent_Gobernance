"use client";

import { useState } from "react";

/** Info button + modal explaining how the session score is computed.
 *
 * The copy is intentionally plain-language: the target reader is any operator
 * with no knowledge of the scoring engine. The math shown mirrors
 * backend/src/domain/scoring (metric catalogue, weighted means, PASS >= 75).
 */
export function ScoringHelpDialog() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="¿Cómo se calcula la puntuación?"
        title="¿Cómo se calcula la puntuación?"
        className="flex h-6 w-6 items-center justify-center rounded-full border border-neutral-300 text-xs font-semibold text-neutral-500 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
      >
        i
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => setOpen(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="scoring-help-title"
            onClick={(event) => event.stopPropagation()}
            className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-6 shadow-xl dark:bg-neutral-900"
          >
            <div className="mb-4 flex items-start justify-between gap-4">
              <h2 id="scoring-help-title" className="text-lg font-semibold">
                ¿Cómo se calcula la puntuación?
              </h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Cerrar"
                className="rounded px-2 py-1 text-sm text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4 text-sm leading-relaxed">
              <p>
                Cada llamada se corrige como un <strong>examen</strong>: se puntúan varias
                cosas de 0 a 100 y se saca la nota final. Esto es exactamente lo que se mira:
              </p>

              <div className="space-y-2">
                <div className="rounded-lg border border-neutral-200 p-3 dark:border-neutral-800">
                  <p className="font-medium">🗣 Conversational — ¿la conversación fue bien?</p>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-neutral-600 dark:text-neutral-400">
                    <li>
                      <strong>¿Se consiguió lo que quería el cliente?</strong> Por ejemplo,
                      que su cita quedara confirmada. Es lo que más importa de toda la
                      llamada.
                    </li>
                    <li>
                      <strong>¿Hablaron los dos?</strong> Si el cliente no llega a hablar, o
                      el agente se queda mudo, algo fue mal.
                    </li>
                    <li>
                      <strong>¿Se terminaron las frases?</strong> Que nadie se quedara a
                      medias al hablar.
                    </li>
                    <li>
                      <strong>¿Hubo silencios incómodos?</strong> Pausas largas en las que
                      nadie decía nada.
                    </li>
                  </ul>
                </div>

                <div className="rounded-lg border border-neutral-200 p-3 dark:border-neutral-800">
                  <p className="font-medium">⚙️ Technical — ¿el sistema funcionó bien?</p>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-neutral-600 dark:text-neutral-400">
                    <li>
                      <strong>¿Contesta sin hacerse esperar?</strong> Si de media tarda
                      segundo y medio o menos en responder, nota perfecta; si tarda más de 3
                      segundos, un cero.
                    </li>
                    <li>
                      <strong>¿Alguna respuesta se hizo eterna?</strong> Se mira la peor de
                      toda la llamada: hasta 3 segundos está bien; más de 5, un cero.
                    </li>
                    <li>
                      <strong>¿Hubo fallos técnicos?</strong> Cortes, errores del
                      sistema… cuantos menos, mejor.
                    </li>
                    <li>
                      <strong>¿La llamada duró lo razonable?</strong> Hasta 5 minutos es
                      perfecto; a partir de 15 puntúa cero.
                    </li>
                  </ul>
                </div>

                <div className="rounded-lg border border-neutral-200 p-3 dark:border-neutral-800">
                  <p className="font-medium">🛡 Seguridad — ¿pasó algo raro?</p>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-neutral-600 dark:text-neutral-400">
                    <li>
                      <strong>¿Alguien intentó algo sospechoso?</strong> Si el sistema
                      detecta un intento de engaño o abuso en la conversación, levanta una
                      bandera. Cada bandera resta 33 puntos.
                    </li>
                    <li>
                      <strong>¿Quedó algún fallo sin arreglar?</strong> Un error del que la
                      llamada no se recuperó.
                    </li>
                    <li>
                      <strong>¿El sistema dio avisos?</strong> Pequeñas alertas internas
                      durante la llamada.
                    </li>
                  </ul>
                  <p className="mt-2 text-neutral-600 dark:text-neutral-400">
                    Aquí <strong>100 es la mejor nota posible</strong>: significa que no pasó
                    absolutamente nada raro.
                  </p>
                </div>
              </div>

              <p>
                Para la nota final se juntan las tres, pero no valen lo mismo:{" "}
                <strong>Seguridad es la que más cuenta</strong> (casi la mitad de la nota),
                después la conversación, y por último la parte técnica:
              </p>

              <p className="rounded-lg bg-neutral-100 p-3 text-center font-mono text-xs dark:bg-neutral-800">
                nota final = conversación ×3 &nbsp;+&nbsp; técnica ×2 &nbsp;+&nbsp; seguridad
                ×4 &nbsp;(÷ 9)
              </p>

              <p>
                La llamada <strong>aprueba (passed) con 75 o más</strong>. Pero ojo: hay 4
                cosas que suspenden directamente, da igual la nota, como quien copia en un
                examen: que la llamada termine con un error grave, que se corte sin llegar a
                acabar, que el cliente no consiguiera lo que pedía, o que quedara un fallo
                sin arreglar.
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
