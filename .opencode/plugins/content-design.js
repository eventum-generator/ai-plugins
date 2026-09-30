/**
 * Content Design plugin for OpenCode.
 *
 * Registers this repository's skills directory with OpenCode and injects the
 * same orientation that SessionStart hooks provide in other agents.
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const skillsDir = path.resolve(__dirname, '../../skills');
const orientationFile = path.join(
  skillsDir,
  'using-content-design',
  'references',
  'orientation.md',
);
const marker = 'CONTENT_DESIGN_ORIENTATION';

let bootstrapCache;

const getBootstrapContent = () => {
  if (bootstrapCache !== undefined) return bootstrapCache;
  try {
    const orientation = fs.readFileSync(orientationFile, 'utf8').trim();
    bootstrapCache = `<${marker}>\n${orientation}\n</${marker}>`;
  } catch {
    bootstrapCache = null;
  }
  return bootstrapCache;
};

export const ContentDesignPlugin = async () => ({
  config: async config => {
    config.skills = config.skills || {};
    config.skills.paths = config.skills.paths || [];
    if (!config.skills.paths.includes(skillsDir)) {
      config.skills.paths.push(skillsDir);
    }
  },

  'experimental.chat.messages.transform': async (_input, output) => {
    const bootstrap = getBootstrapContent();
    if (!bootstrap || !output.messages.length) return;

    const firstUser = output.messages.find(message => message.info.role === 'user');
    if (!firstUser || !firstUser.parts.length) return;
    if (firstUser.parts.some(part => part.type === 'text' && part.text.includes(marker))) {
      return;
    }

    const ref = firstUser.parts[0];
    firstUser.parts.unshift({ ...ref, type: 'text', text: bootstrap });
  },
});
