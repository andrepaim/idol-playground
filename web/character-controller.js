// Metres, Y-up: x/z translation and yaw. Pure logic; no renderer or GPU ownership.
const STEP = 1 / 60;
const MAX_CATCH_UP = .25;
function positive(value, name) {
  if (!Number.isFinite(value) || value <= 0) throw new Error(`${name} must be finite and positive.`);
  return value;
}
function approach(value, target, amount) {
  return value + Math.sign(target - value) * Math.min(Math.abs(target - value), amount);
}

export class CharacterController {
  #time = 0;
  #vx = 0;
  #vz = 0;
  #obstacles;
  constructor({maxSpeed = 2, acceleration = 8, radius = .3, turnRate = 8, obstacles = []} = {}) {
    this.maxSpeed = positive(maxSpeed, 'maxSpeed');
    this.acceleration = positive(acceleration, 'acceleration');
    this.radius = positive(radius, 'radius');
    this.turnRate = positive(turnRate, 'turnRate');
    // Conservative square footprint, expanded against AABBs for continuous axis sweeps.
    this.#obstacles = obstacles.map(box => {
      const copy = {minX: box.minX, maxX: box.maxX, minZ: box.minZ, maxZ: box.maxZ};
      if (!Object.values(copy).every(Number.isFinite) || copy.minX >= copy.maxX || copy.minZ >= copy.maxZ) {
        throw new Error('Invalid obstacle bounds.');
      }
      if (copy.minX - radius < 0 && copy.maxX + radius > 0 && copy.minZ - radius < 0 && copy.maxZ + radius > 0) {
        throw new Error('Obstacle overlaps the reset position.');
      }
      return copy;
    });
    this.reset();
  }
  reset() {
    this.x = this.z = this.yaw = this.speed = this.#vx = this.#vz = this.#time = 0;
  }
  update(delta, {x = 0, z = 0} = {}) {
    if (![delta, x, z].every(Number.isFinite) || delta < 0) throw new Error('Invalid controller input.');
    const length = Math.max(1, Math.hypot(x, z));
    x /= length; z /= length;
    this.#time += Math.min(delta, MAX_CATCH_UP);
    while (this.#time + 1e-12 >= STEP) {
      this.#time = Math.max(0, this.#time - STEP);
      const targetX = x * this.maxSpeed, targetZ = z * this.maxSpeed;
      const distance = Math.hypot(targetX - this.#vx, targetZ - this.#vz);
      const amount = distance ? Math.min(1, this.acceleration * STEP / distance) : 0;
      this.#vx += (targetX - this.#vx) * amount;
      this.#vz += (targetZ - this.#vz) * amount;
      const oldX = this.x, oldZ = this.z;
      this.x = this.#sweep(this.x, this.z, this.#vx * STEP, 'X', 'Z');
      this.z = this.#sweep(this.z, this.x, this.#vz * STEP, 'Z', 'X');
      this.speed = Math.hypot(this.x - oldX, this.z - oldZ) / STEP;
      if (this.speed > 1e-8) {
        const heading = Math.atan2(this.x - oldX, this.z - oldZ);
        const difference = Math.atan2(Math.sin(heading - this.yaw), Math.cos(heading - this.yaw));
        this.yaw += approach(0, difference, this.turnRate * STEP);
      }
    }
    return this;
  }
  #sweep(position, tangent, distance, axis, other) {
    let next = position + distance;
    for (const box of this.#obstacles) {
      if (tangent <= box[`min${other}`] - this.radius || tangent >= box[`max${other}`] + this.radius) continue;
      const low = box[`min${axis}`] - this.radius, high = box[`max${axis}`] + this.radius;
      if (distance > 0 && position <= low && next > low) next = low;
      if (distance < 0 && position >= high && next < high) next = high;
    }
    return next;
  }
}
