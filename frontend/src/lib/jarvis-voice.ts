export type JarvisVoiceCommand = {
  detected: true;
  command: string;
};

export type JarvisVoiceIntent =
  | { type: 'navigate'; path: string; label: string }
  | { type: 'chat'; command: string };

function normalizeVoiceText(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[¿?¡!.,;:]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function extractJarvisVoiceCommand(
  transcript: string,
): JarvisVoiceCommand | null {
  const text = transcript.trim();
  if (!text) return null;

  const mergedWakeAndOpen = text.match(/^\s*y\s+sabr[eé]\s+(.+)/i)
    ?? text.match(/^\s*ya\s+arbisabre\s+(.+)/i);
  if (mergedWakeAndOpen) {
    const object = (mergedWakeAndOpen[1] ?? '')
      .split(/[.!?]/, 1)[0]
      ?.split(/\s+(?:jarvis|yarvis|jervis|harvis|ya\s+arbisabre|ya\s+arbis|ya\s+arvis|y\s+arv[ií]|y\s+sabr[eé])\b/i, 1)[0]
      ?.trim() ?? '';
    return { detected: true, command: object ? `abre ${object}` : 'abre' };
  }

  const wake = text.match(
    /(?:\bjarvis\b|\byarvis\b|\bjervis\b|\bharvis\b|\barbis\b|\bya\s+arbis|\by\s+arbis|\bya\s+arvis|\by\s+arv[ií])/i,
  );
  if (!wake || wake.index === undefined) return null;

  let command = text
    .slice(wake.index + wake[0].length)
    .replace(/^[\s,:-]+/, '')
    .trim();
  command = command
    .replace(/^sabr[eé]\b/i, 'abre')
    .replace(/^habr[ií]a\b/i, 'abre');
  command = command
    .split(/\s+(?:jarvis|yarvis|jervis|harvis|ya\s+arbisabre|ya\s+arbis|ya\s+arvis|y\s+arv[ií]|y\s+sabr[eé])\b/i, 1)[0]
    ?.trim() ?? command;

  return { detected: true, command };
}

export function resolveJarvisVoiceIntent(command: string): JarvisVoiceIntent {
  const normalized = normalizeVoiceText(command);
  const openPrefix = '(?:abre|abrir|muestra|mostrar|ve a|ir a|entra a|quiero ver)';

  const navigation: Array<{ pattern: RegExp; path: string; label: string }> = [
    {
      pattern: new RegExp(`^${openPrefix}\\s+(?:los\\s+)?agentes?$`),
      path: '/agents',
      label: 'Agentes',
    },
    {
      pattern: new RegExp(`^${openPrefix}\\s+(?:el\\s+)?(?:dashboard|panel|tablero)(?:\\s+principal)?$`),
      path: '/dashboard',
      label: 'Dashboard',
    },
    {
      pattern: new RegExp(`^${openPrefix}\\s+(?:la\\s+)?(?:configuracion|ajustes|settings)$`),
      path: '/settings',
      label: 'Configuración',
    },
    {
      pattern: new RegExp(`^${openPrefix}\\s+(?:los\\s+)?(?:logs|registros)$`),
      path: '/logs',
      label: 'Logs',
    },
    {
      pattern: new RegExp(`^${openPrefix}\\s+(?:las\\s+)?(?:fuentes de datos|origenes de datos|data sources)$`),
      path: '/data-sources',
      label: 'Fuentes de datos',
    },
    {
      pattern: new RegExp(`^${openPrefix}\\s+(?:el\\s+)?(?:chat|conversacion|inicio)$`),
      path: '/',
      label: 'Chat',
    },
    {
      pattern: new RegExp(`^${openPrefix}\\s+(?:la\\s+)?(?:guia inicial|configuracion inicial|get started)$`),
      path: '/get-started',
      label: 'Inicio guiado',
    },
  ];

  const match = navigation.find((item) => item.pattern.test(normalized));
  if (match) {
    return { type: 'navigate', path: match.path, label: match.label };
  }
  return { type: 'chat', command: command.trim() };
}
