import test from 'node:test';
import assert from 'node:assert/strict';
import { CharacterController } from '../../web/character-controller.js';

function drive(hz, input, options = {}, seconds = 3) {
  const controller = new CharacterController(options);
  for (let i = 0; i < hz * seconds; i++) controller.update(1 / hz, input);
  return controller;
}
test('normalizes diagonal input without changing speed', () => {
  const straight = drive(60, {x: 1, z: 0});
  const diagonal = drive(60, {x: 1, z: 1});
  assert.ok(Math.abs(straight.x - Math.hypot(diagonal.x, diagonal.z)) < 1e-9);
});
test('fixed simulation produces equal travel across render schedules', () => {
  const distances = [30, 60, 120].map(hz => drive(hz, {x: .5, z: -1}).z);
  assert.ok(Math.max(...distances) - Math.min(...distances) < 1e-9);
});
test('swept collision blocks thin walls and permits tangential motion', () => {
  const wall = {minX: 1, maxX: 1.01, minZ: -10, maxZ: 10};
  const controller = drive(60, {x: 1, z: 1}, {obstacles: [wall], radius: .25});
  assert.ok(controller.x <= .75);
  assert.ok(controller.z > 2);
});
test('blocked movement reports actual speed for animation', () => {
  const controller = drive(60, {x: 1, z: 0}, {obstacles: [{minX: 1, maxX: 2, minZ: -10, maxZ: 10}]});
  assert.equal(controller.speed, 0);
});
test('coasts to a stop and stays still; reset clears motion and fractional time', () => {
  const controller = drive(60, {x: 1, z: 0});
  for (let i = 0; i < 120; i++) controller.update(1 / 60, {});
  const stopped = controller.x;
  controller.update(1 / 60, {});
  assert.equal(controller.x, stopped);
  controller.update(.001, {x: 1});
  controller.reset();
  assert.equal(controller.x, 0);
  assert.equal(controller.speed, 0);
  controller.update(.001, {x: 1});
  assert.equal(controller.x, 0);
});
test('tab-resume catch-up is bounded and invalid delta/input cannot poison state', () => {
  const controller = new CharacterController();
  controller.update(3600, {x: 1});
  assert.ok(controller.x < 1);
  assert.throws(() => controller.update(NaN, {}));
  assert.throws(() => controller.update(.1, {x: Infinity}));
  assert.throws(() => controller.update(-1, {}));
  assert.ok(Number.isFinite(controller.x));
});
test('validates configuration and copies obstacle data', () => {
  for (const options of [{radius: 0}, {maxSpeed: NaN}, {acceleration: -1}, {obstacles: [{minX: 3, maxX: 2, minZ: 0, maxZ: 1}]}]) {
    assert.throws(() => new CharacterController(options));
  }
  const obstacles = [{minX: 1, maxX: 2, minZ: -10, maxZ: 10}];
  const controller = new CharacterController({obstacles});
  obstacles[0].minX = 100;
  for (let i = 0; i < 120; i++) controller.update(1/60, {x: 1});
  assert.ok(controller.x < 1);
});
