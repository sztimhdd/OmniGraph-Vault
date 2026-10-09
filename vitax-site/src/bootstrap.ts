/**
 * Startup gate for the reader.
 *
 * The built page may already contain prerendered markup. That markup stays
 * visible and untouched until `/api/release` has been confirmed by the read
 * service; only then does the reader deliberately replace it with the
 * API-backed React render. A failed bootstrap replaces it with one bounded
 * global error instead.
 */
import type {KnowledgeApi} from './api.ts';
import type {Release} from './types.ts';

export interface ReaderMount {
  /** Remove the prerendered markup. Only called once the bootstrap attempt settles. */
  clearPrerendered: () => void;
  renderReader: (release: Release) => void;
  renderBootstrapFailure: (error: Error) => void;
}

export async function startReader(
  api: Pick<KnowledgeApi, 'bootstrap'>,
  mount: ReaderMount,
): Promise<'ready' | 'failed'> {
  try {
    const release = await api.bootstrap();
    mount.clearPrerendered();
    mount.renderReader(release);
    return 'ready';
  } catch (error) {
    mount.clearPrerendered();
    mount.renderBootstrapFailure(error instanceof Error ? error : new Error(String(error)));
    return 'failed';
  }
}
