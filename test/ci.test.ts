import * as fs from 'fs';
import * as path from 'path';

test('gitlab CI defines a unit-test job', () => {
  const ci = fs.readFileSync(path.join(__dirname, '..', '.gitlab-ci.yml'), 'utf8');
  expect(ci).toMatch(/^unit-test:/m);
});

test('Dockerfile exists and is multi-stage', () => {
  const df = fs.readFileSync(path.join(__dirname, '..', 'Dockerfile'), 'utf8');
  expect(df).toContain('FROM node:20');
  expect((df.match(/FROM/g) || []).length).toBeGreaterThanOrEqual(2);
});
