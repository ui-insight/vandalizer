//selecting all required elements
const dropArea = document.querySelector(".drag-area"),
  dragText = dropArea.querySelector("header"),
  button = dropArea.querySelector("button"),
  input = dropArea.querySelector("input");
const dragTextArea = $("#drag-area-text");
const processingIndicator = $("#loading-area");
const processingtext = $("#processing-text");
const instructiontext = $("#instruction-text");
var processingNumber = 0;
var processingComplete = 0;
var numRequests = 0;
var filesToUpload = {};

let file; //this is a global variable and we'll use it inside multiple functions

input.addEventListener("change", function () {
  //getting user select file and [0] this means if user select multiple files then we'll select only the first one
  file = this.files[0];
  dropArea.classList.add("active");
  console.log("I am here");
  //showFile(); //calling function
});

//If user Drag File Over DropArea
dropArea.addEventListener("dragover", (event) => {
  event.preventDefault(); //preventing from default behaviour
  dropArea.classList.add("active");
  dragText.textContent = "Release to Upload File";
});

//If user leave dragged File from DropArea
dropArea.addEventListener("dragleave", () => {
  dropArea.classList.remove("active");
  dragText.textContent = "Drag & Drop to Upload File";
});

//If user drop File on DropArea
dropArea.addEventListener("drop", (event) => {
  event.preventDefault(); //preventing from default behaviour
  //getting user select file and [0] this means if user select multiple files then we'll select only the first one
  processingNumber = 0;
  processingComplete = 0;
  handleDrop(event);
  dragTextArea.hide();
  processingIndicator.show();
  processingIndicator.css("display", "flex");

  //showFile(); //calling function
});

function updateCount() {
  processingtext.text(
    "Remaining: " + Object.keys(filesToUpload).length + " sightings"
  );
}

function showInvalidFileError() {
  $('#processing-text').text("Invalid file(s) detected. Please try again by dragging and dropping the topmost folder.");
}

async function handleDrop(e) {
  e.preventDefault();

  console.log("Sending notification");
  $.ajax({
    type: "POST",
    url: "/notify",
    processData: false,
    contentType: false,
    dataType: "json",
    success: function (result) {
    },
    error: function (err) {
      console.log("ERROR: ", err);
    },
  });

  // Get all the items in the DataTransfer object
  const items = Array.from(e.dataTransfer.items);
  // Create a variable to store the folders
  var folders = [];

  // Loop through the items in the dataTransfer object
  for (var i = 0; i < e.dataTransfer.items.length; i++) {
    // Get the folder from the current item
    var folder = e.dataTransfer.items[i].webkitGetAsEntry();

    // Add the folder to the array of folders
    
    if (folder instanceof FileSystemDirectoryEntry) {
      var split = folder.name.split("_");
      if (split.length == 5 || split.length == 6) {
        folders.push(folder);
      } else {
        showInvalidFileError();
        return
      }
    } else {
      showInvalidFileError();
      return
    }
  }

  
  for (var i = 0; i < folders.length; i++) {
    var zip = new JSZip();
    var entry = folders[i];
    if (entry != null && entry.isDirectory) {
      await processDirectory('', entry, zip);
    } else if (entry != null && entry.isFile) {
      await processFile(entry, "", zip);
    }

    const content = await zip.generateAsync({ type: "blob" });
    uploadZip(content, entry.name + ".zip");
    //saveAs(content, entry.name + ".zip");
  }
}

async function processDirectory(dirName, dirEntry, zip) {
  
  const dirReader = dirEntry.createReader();
  let entries = await readEntriesPromise(dirReader);
  while (entries.length > 0) {
    for (const entry of entries) {
      if (entry.isFile) {
        if (dirName == "") {
          await processFile(entry, dirEntry.name, zip);
        } else {
          await processFile(entry, dirName + "/" + dirEntry.name, zip);
        }
      } else if (entry.isDirectory) {
        if (dirName == "") {
          await processDirectory(dirEntry.name, entry, zip);
        } else {
          await processDirectory(dirName + "/" + dirEntry.name, entry, zip);
        }
      }
    }
    entries = await readEntriesPromise(dirReader);
  }
}

function readEntriesPromise(dirReader) {
  return new Promise((resolve, reject) => {
    dirReader.readEntries(resolve, reject);
  });
}

function createBlob(data) {
  return new Blob([data], { type: "text/plain" });
}

async function processFile(fileEntry, dirName, zip) {
  // get file
  var filetype = fileEntry.type;

  const file = await new Promise((resolve, reject) => {
    fileEntry.file(resolve, reject);
  });

  var blob = new Blob([file], { type: filetype });
  zip.file(dirName + "/" + fileEntry.name, blob);
}

$("#loading-area")
  .hide() // Hide it initially
  .ajaxStart(function () {
    $(this).show();
  });

// // Function to upload files
function uploadFile(fileObject, directoryName) {
  var filetype = fileObject.type;
  var filename = fileObject.name;

  var blob = new Blob([fileObject], { type: filetype });
  var reader = new FileReader();
  if (fileObject instanceof Blob) {
    filesToUpload[directoryName + "/" + filename] = true;
    reader.readAsDataURL(fileObject);
    reader.onload = function () {
      const base64String = reader.result.split(",")[1];
      var options = $("#change-deployment-select")[0].options;
      var deployment = options[options.selectedIndex].id;
      var model = {
        contentType: filetype,
        contentAsBase64String: base64String,
        fileName: filename,
        directory: directoryName,
        deploymentId: deployment,
      };

      numRequests++;
      // Create an XMLHttpRequest object
      $.ajax({
        type: "POST",
        url: "/upload_file",
        data: JSON.stringify(model),
        processData: false,
        contentType: "application/json",
        dataType: "json",
        success: function (result) {
          numRequests--;
          processingComplete++;
          updateCount();
          delete filesToUpload[directoryName + "/" + filename];
          checkInternetConnection();
          if (Object.keys(filesToUpload).length == 0) {
            dragTextArea.show();
            processingIndicator.hide();
            instructiontext[0].innerHTML =
              "Your data has been uploaded, you can delete it from your flash drive.<br> <a href='/home'>Click to see what you've found</a>";
          }

          checkForIssues();
        },
        error: function (err) {
          console.log("ERROR: ", err);
          numRequests--;
          checkForIssues();
        },
      });
    };
  }
  //adding that created img tag inside dropArea container
}

function uploadZip(zipFile, name) {
  var formData = new FormData();
  formData.append('file', zipFile, name);
  filesToUpload[name] = zipFile;
  var options = $("#change-deployment-select")[0].options;
  var deployment = options[options.selectedIndex].id;    
  var data = {
    deploymentId: deployment,
  };
  
  formData.append('json', JSON.stringify(data));
  numRequests++;
  updateCount();
  // Create an XMLHttpRequest object
  $.ajax({
    type: "POST",
    url: "/upload_zip",
    data: formData,
    processData: false,
    contentType: false,
    dataType: "json",
    success: function (result) {
      numRequests--;
      processingComplete++;
      
      delete filesToUpload[name];
      updateCount();
      checkInternetConnection();
      checkForIssues();
      if (Object.keys(filesToUpload).length == 0) {
        dragTextArea.show();
        processingIndicator.hide();
        instructiontext[0].innerHTML =
          "Your data has been uploaded, you can delete it from your flash drive.<br> <a href='/home'>Click to see what you've found</a>";
      }
    },
    error: function (err) {
      console.log("ERROR: ", err);
      numRequests--;
      checkForIssues();
    },
  });
  //adding that created img tag inside dropArea container
}

function checkForIssues() {
  if (numRequests == 0 && Object.keys(filesToUpload).length > 0) {
    console.log("Found an issue");
    for (const [key, value] of Object.entries(filesToUpload)) {
      uploadZip(filesToUpload[key], key);
    }
  }
}

function getB64Str(buffer) {
  var binary = "";
  var bytes = new Uint8Array(buffer);
  var len = bytes.byteLength;
  for (var i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}

$("#change-deployment-select").on("change", function (e) {
  e.preventDefault();
  var options = $("#change-deployment-select")[0].options;
  var selection = options[options.selectedIndex].id;
  console.log(selection);
  if (selection == "add-new-deployment") {
    location.href = "/deployments/new";
  }
});

function checkInternetConnection() {
  if (!navigator.onLine) {
    instructiontext.text(
      "You've lost your internet connection, please reconnect and try again"
    );
  }
}
