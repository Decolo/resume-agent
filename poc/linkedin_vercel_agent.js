#!/usr/bin/env node
/**
 * LinkedIn Browser Control POC using Vercel Agent Browser
 *
 * Uses AI-powered browser automation instead of hardcoded selectors.
 * Connects to a running Chrome instance via CDP.
 *
 * Installation:
 *   npm install -g agent-browser
 *   agent-browser install
 *
 * Usage:
 *   node poc/linkedin_vercel_agent.js "Your post content"
 */

import { spawn } from 'child_process';

async function postToLinkedInWithAgent(content) {
  return new Promise((resolve, reject) => {
    console.log('Connecting to Chrome via agent-browser...');

    // Connect to existing Chrome on port 9222
    const agent = spawn('agent-browser', ['connect', '9222'], {
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    let output = '';
    let errorOutput = '';

    agent.stdout.on('data', (data) => {
      output += data.toString();
      console.log(data.toString());
    });

    agent.stderr.on('data', (data) => {
      errorOutput += data.toString();
      console.error(data.toString());
    });

    // Send AI instructions to the agent
    const instructions = [
      'navigate to https://www.linkedin.com/feed/',
      'click the "Start a post" button',
      `type "${content}" in the post editor`,
      'click the "Post" button',
      'wait 2 seconds',
      'exit',
    ].join('\n');

    agent.stdin.write(instructions + '\n');
    agent.stdin.end();

    agent.on('close', (code) => {
      if (code === 0) {
        console.log('✓ Post submitted successfully!');
        resolve(true);
      } else {
        console.error(`✗ Agent exited with code ${code}`);
        console.error(errorOutput);
        reject(new Error(`Agent failed with code ${code}`));
      }
    });

    agent.on('error', (err) => {
      console.error('✗ Failed to start agent-browser:', err);
      reject(err);
    });
  });
}

// Main execution
const content = process.argv[2] || 'Test post from Vercel Agent Browser POC';

postToLinkedInWithAgent(content)
  .then(() => process.exit(0))
  .catch((err) => {
    console.error(err);
    process.exit(1);
  });
