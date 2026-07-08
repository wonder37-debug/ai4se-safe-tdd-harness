module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  testMatch: ['**/test/**/*.test.ts', '**/demo/**/*.test.ts'],
  testPathIgnorePatterns: ['<rootDir>/.claude/'],
  testTimeout: 15000,
};
