import { describe, expect, it } from 'vitest';
import {
  extractJarvisVoiceCommand,
  resolveJarvisVoiceIntent,
} from '../../lib/jarvis-voice';

describe('extractJarvisVoiceCommand', () => {
  it('extracts a clean direct Jarvis command', () => {
    expect(extractJarvisVoiceCommand('Jarvis abre agentes')).toEqual({
      detected: true,
      command: 'abre agentes',
    });
  });

  it('handles Whisper Spanish variant "Ya arbis"', () => {
    expect(extractJarvisVoiceCommand('Ya arbis habría agentes.')).toEqual({
      detected: true,
      command: 'abre agentes.',
    });
  });

  it('handles concatenated wake + command from MediaRecorder', () => {
    expect(extractJarvisVoiceCommand('Ya arbisabre agentes. Ya arbisabre...')).toEqual({
      detected: true,
      command: 'abre agentes',
    });
  });

  it('handles merged Whisper variant "Y sabré"', () => {
    expect(extractJarvisVoiceCommand('y sabré agentes. Y arví sabré agentes.')).toEqual({
      detected: true,
      command: 'abre agentes',
    });
  });

  it('arms when only the wake word is heard', () => {
    expect(extractJarvisVoiceCommand('Jarvis')).toEqual({
      detected: true,
      command: '',
    });
  });

  it('ignores unrelated speech', () => {
    expect(extractJarvisVoiceCommand('abre agentes')).toBeNull();
  });

  it('routes direct UI navigation commands without using the model', () => {
    expect(resolveJarvisVoiceIntent('abre agentes')).toEqual({
      type: 'navigate',
      path: '/agents',
      label: 'Agentes',
    });
    expect(resolveJarvisVoiceIntent('abre configuración')).toEqual({
      type: 'navigate',
      path: '/settings',
      label: 'Configuración',
    });
    expect(resolveJarvisVoiceIntent('muestra fuentes de datos')).toEqual({
      type: 'navigate',
      path: '/data-sources',
      label: 'Fuentes de datos',
    });
  });

  it('keeps non-navigation voice commands in chat', () => {
    expect(resolveJarvisVoiceIntent('resume mis tareas de hoy')).toEqual({
      type: 'chat',
      command: 'resume mis tareas de hoy',
    });
  });
});
