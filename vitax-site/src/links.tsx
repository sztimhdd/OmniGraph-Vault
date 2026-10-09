/** Client-side navigation helpers: real anchors, intercepted only for plain clicks. */
import {createContext, useContext, type MouseEvent, type ReactNode} from 'react';

export type Navigate = (path: string) => void;

const NavigationContext = createContext<Navigate>(() => undefined);

export const NavigationProvider = NavigationContext.Provider;

export function useNavigate(): Navigate {
  return useContext(NavigationContext);
}

interface NavLinkProps {
  to: string;
  className?: string;
  children: ReactNode;
}

/**
 * Renders a real anchor so new-tab/middle-click/copy-link keep working, and
 * uses the history API for plain left clicks.
 */
export function NavLink({to, className, children}: NavLinkProps) {
  const navigate = useNavigate();
  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }
    event.preventDefault();
    navigate(to);
  };
  return (
    <a href={to} className={className} onClick={handleClick}>
      {children}
    </a>
  );
}
