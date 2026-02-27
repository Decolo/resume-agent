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
 *   node poc/linkedin_vercel_agent.js "Your post content" --port 9222
 *   node poc/linkedin_vercel_agent.js "Your post content" --dry-run
 */

import { spawn } from 'child_process';

function parseArgs() {
  const args = process.argv.slice(2);
  const config = {
    content: null,
    port: '9222',
    dryRun: false,
  };

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--port' && args[i + 1]) {
      config.port = args[++i];
    } else if (args[i] === '--dry-run') {
      config.dryRun = true;
    } else if (!config.content) {
      config.content = args[i];
    }
  }

  return config;
}

async function postToLinkedInWithAgent(content, port = '9222', dryRun = false) {
  return new Promise((resolve, reject) => {
    console.log(`Connecting to Chrome on port ${port} via agent-browser...`);

    if (dryRun) {
      console.log('[DRY RUN] Would execute the following instructions:');
      console.log('  1. Navigate to https://www.linkedin.com/feed/');
      console.log('  2. Click the "Start a post" button');
      console.log(`  3. Type "${content}" in the post editor`);
      console.log('  4. Click the "Post" button');
      console.log('\n✓ Dry run completed. Use without --dry-run to actually post.');
      resolve(true);
      return;
    }

    // Connect to existing Chrome on specified port
    const agent = spawn('agent-browser', ['connect', port], {
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    let output = '';
    let errorOutput = '';

    agent.stdout.on('data', (data) => {
      const text = data.toString();
      output += text;
      process.stdout.write(text);
    });

    agent.stderr.on('data', (data) => {
      const text = data.toString();
      errorOutput += text;
      process.stderr.write(text);
    });

    // Send AI instructions to the agent
    const instructions = [
      'navigate to https://www.linkedin.com/feed/',
      'wait for page to load',
      'click the "Start a post" button',
      'wait 1 second',
      `type "${content.replace(/"/g, '\\"')}" in the post editor`,
      'wait 1 second',
      'click the "Post" button',
      'wait 3 seconds',
      'exit',
    ].join('\n');

    console.log('\nSending instructions to AI agent...\n');
    agent.stdin.write(instructions + '\n');
    agent.stdin.end();

    agent.on('close', (code) => {
      if (code === 0) {
        console.log('\n✓ Post submitted successfully!');
        resolve(true);
      } else {
        console.error(`\n✗ Agent exited with code ${code}`);
        if (errorOutput) {
          console.error('Error details:', errorOutput);
        }
        reject(new Error(`Agent failed with code ${code}`));
      }
    });

    agent.on('error', (err) => {
      console.error('✗ Failed to start agent-browser:', err.message);
      console.error('\nMake sure agent-browser is installed:');
      console.error('  npm install -g agent-browser');
      console.error('  agent-browser install');
      reject(err);
    });
  });
}

// Main execution
const config = parseArgs();

if (!config.content) {
  console.error('Usage: node linkedin_vercel_agent.js "Your post content" [--port 9222] [--dry-run]');
  console.error('\nOptions:');
  console.error('  --port <port>  CDP port (default: 9222)');
  console.error('  --dry-run      Show what would be posted without actually posting');
  console.error('\nMake sure Chrome is running with:');
  console.error('  google-chrome --remote-debugging-port=9222');
  process.exit(1);
}

postToLinkedInWithAgent(config.content, config.port, config.dryRun)
  .then(() => process.exit(0))
  .catch((err) => {
    console.error('\n✗ Error:', err.message);
    process.exit(1);
  });
