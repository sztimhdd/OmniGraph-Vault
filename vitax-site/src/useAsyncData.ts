import {useCallback, useEffect, useState} from 'react';

export type AsyncState<T> =
  | {status: 'loading'}
  | {status: 'ready'; value: T}
  | {status: 'error'; error: Error};

export interface AsyncResult<T> {
  state: AsyncState<T>;
  retry: () => void;
}

/** Run one read and expose its loading/ready/error states with an explicit retry. */
export function useAsyncData<T>(load: () => Promise<T>, deps: readonly unknown[]): AsyncResult<T> {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<AsyncState<T>>({status: 'loading'});

  useEffect(() => {
    let active = true;
    setState({status: 'loading'});
    load().then(
      (value) => {
        if (active) setState({status: 'ready', value});
      },
      (error: unknown) => {
        if (active) setState({status: 'error', error: error instanceof Error ? error : new Error(String(error))});
      },
    );
    return () => {
      active = false;
    };
    // `load` is intentionally excluded: callers pass the dependency list that
    // describes the read (route, identifier), and `attempt` drives retries.
  }, [...deps, attempt]);

  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  return {state, retry};
}
