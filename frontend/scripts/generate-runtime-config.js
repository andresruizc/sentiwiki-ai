#!/usr/bin/env node
/**
 * Generate runtime configuration file for Next.js frontend
 * 
 * This script reads environment variables at RUNTIME (not build time)
 * and creates a config file that can be read by both server and client.
 * 
 * Why this is needed:
 * - Next.js replaces NEXT_PUBLIC_* vars at BUILD TIME
 * - We need to read the API URL at RUNTIME from ECS task definition
 * - This allows the same Docker image to work with different API URLs
 */

const fs = require('fs');
const path = require('path');

// Read API URL from environment variable (set in ECS task definition)
const apiUrl = process.env.NEXT_PUBLIC_API_URL || process.env.API_URL || 'http://localhost:8002';
const env = process.env.NEXT_PUBLIC_ENV || process.env.NODE_ENV || 'production';

// Create config object
const config = {
  API_URL: apiUrl,
  ENV: env,
};

// Ensure public directory exists
const publicDir = path.join(__dirname, '..', 'public');
if (!fs.existsSync(publicDir)) {
  fs.mkdirSync(publicDir, { recursive: true });
}

// Write config file
const configPath = path.join(publicDir, 'runtime-config.json');
fs.writeFileSync(configPath, JSON.stringify(config, null, 2));

console.log('✅ Runtime config generated:');
console.log(`   API_URL: ${apiUrl}`);
console.log(`   ENV: ${env}`);
console.log(`   File: ${configPath}`);

