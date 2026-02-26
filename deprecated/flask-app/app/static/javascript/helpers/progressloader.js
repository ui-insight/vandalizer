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
    this.loadingIcon = this.rootContainer.querySelector("#loading-event-icon");
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

  hideProgressBar() {
    this.progressBarEl.style.display = "none";
    this.progressFillEl.style.display = "none";
  }

  showDefaultMessage() {
    this.loadingIcon.classList = "fa-solid fa-file-import";
    this.messageEl.textContent = "Let’s get started!";
    this.subMessageEl.textContent = "Upload or select one or more documents, or simply ask me a question."
    this.hideProgressBar();
  }

  showOCRMessage() {
    this.loadingIcon.classList = "fa-solid fa-cogs fa-spin";
    this.messageEl.textContent = "Converting And Preparing Your Document…";
    this.subMessageEl.textContent = "We’re converting it can be read and analyzed accurately.";
    this.hideProgressBar();
  }

  showSecurityMessage() {
    this.loadingIcon.classList = "fa-solid fa-shield-alt fa-spin";
    this.messageEl.textContent = "Scanning Your Document for Security…";
    this.subMessageEl.textContent = "Please hang tight—we’re checking for any sensitive information we need to keep safe."
    this.hideProgressBar();
  }

  showSecurityFailureMessage() {
    this.loadingIcon.classList = "fa-solid fa-lock fa-spin";
    this.messageEl.textContent = "Document is locked by security check…";
    this.subMessageEl.textContent = "We detected sensitive information in your document and are securing all AI calls for you."
    this.hideProgressBar();
  }

  showRecommendationMessage() {
    
    this.loadingIcon.classList = "fa-solid fa-tasks fa-spin";
    this.messageEl.textContent = "Finding Recommended Tasks & Workflows…";
    this.subMessageEl.textContent = "Hang tight—we’re analyzing your document to surface the best next steps."
    this.hideProgressBar();
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

  fastHide() {
    this.rootContainer.style.display = "none";
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