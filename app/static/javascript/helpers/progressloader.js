class ProgressLoader {
  /**
   * @param {string} containerSelector - The selector for the root container of the progress loader.
   */
  constructor(containerSelector) {
    this.rootContainer = document.querySelector(containerSelector);
    if (!this.rootContainer) {
      console.error(`ProgressLoader: Container with selector "${containerSelector}" not found.`);
      return;
    }

    // DOM element references
    this.messageEl = this.rootContainer.querySelector("#loading-event-title");
    this.subMessageEl = this.rootContainer.querySelector("#loading-event-message");
    this.progressFillEl = this.rootContainer.querySelector(".loading-progress-fill");
    this.progressBarEl = this.rootContainer.querySelector(".loading-progress-bar");

    // Internal state
    this.progress = 0;
    this.itemIdentifier = 0;
  }

  /**
   * Shows the loader with a fade-in effect.
   */
  show() {
    this.rootContainer.style.display = "block";
    this.rootContainer.classList.remove("fade-out");
    this.rootContainer.classList.add("fade-in");
  }

  /**
   * Hides the loader with a fade-out effect.
   */
  hide() {
    this.rootContainer.classList.add("fade-out");
    setTimeout(() => {
      this.rootContainer.style.display = "none";
    }, 500); // Match fade-out duration
  }

  /**
   * Sets the main message and optional sub-message.
   * @param {string} message - The primary message.
   * @param {string} [subMessage] - The secondary message.
   */
  setMessage(message, subMessage = "") {
    if (this.messageEl) {
      this.messageEl.textContent = message;
    }
    if (this.subMessageEl) {
      this.subMessageEl.textContent = subMessage;
    }
  }

  /**
   * Sets the progress bar to a specific value.
   * @param {number} percent - A number between 0 and 100.
   */
  setProgress(percent) {
    const clamped = Math.max(0, Math.min(100, percent));
    this.progress = clamped;
    if (this.progressFillEl) {
      this.progressFillEl.style.width = `${clamped}%`;
      // Reset status classes when manually setting progress
      this.progressFillEl.classList.remove("progress-loader-completed", "progress-loader-failed");
    }
  }

  /**
   * Increments the progress bar by a given amount.
   * @param {number} amount - The amount to add to the current progress.
   */
  incrementProgress(amount) {
    this.setProgress(this.progress + amount);
  }

  /**
   * Marks the loader as completed.
   * @param {string} [message] - Optional final message.
   * @param {string} [subMessage] - Optional final sub-message.
   */
  markCompleted(message = "Completed successfully ✅", subMessage = "") {
    this.setProgress(100);
    if (this.progressFillEl) {
      this.progressFillEl.classList.add("progress-loader-completed");
    }
    this.setMessage(message, subMessage);
  }

  /**
   * Marks the loader as failed.
   * @param {string} [message] - Optional error message.
   * @param {string} [subMessage] - Optional second-line message.
   */
  markFailed(message = "An error occurred ❌", subMessage = "") {
    this.setProgress(100);
    if (this.progressFillEl) {
      this.progressFillEl.classList.add("progress-loader-failed");
    }
    this.setMessage(message, subMessage);
  }
}