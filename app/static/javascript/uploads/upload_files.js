let pendingUploads = 0;
let completedUploads = 0;
const uploadedDocs = [];
var rootFolderName = null; // Variable to store the root folder name

var file;
let fileInput = document.querySelector("#file-input");
let dropArea = document.querySelector(".drag-area");
let dragText = dropArea.querySelector("header");

if (dropArea) {  
    //button = dropArea.querySelector("button"),
    input = dropArea.querySelector("input"),
    dragArea = document.querySelector(".drop-area");
  //this is a global variable and we'll use it inside multiple functions
  //button.onclick = ()=>{
  //  input.click(); //if user click on the button then the input also clicked
  //}
  input.addEventListener("change", function () {
    //getting user select file and [0] this means if user select multiple files then we'll select only the first one
    file = this.files[0];
    dropArea.classList.add("active");
    showFile(); //calling function
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
    dragText.textContent = "Drag & Drop to Upload Files";
  });

  //If user drop File on DropArea
  dropArea.addEventListener("drop", e => {
  e.preventDefault();
  dropArea.classList.remove("active");
  dragText.textContent = "Drag & Drop to Upload Files";

  const items = e.dataTransfer.items;
  if (items && items.length) {
    // Reset before we inspect
    rootFolderName = null;
    pendingUploads   = items.length;
  completedUploads = 0;

    for (let i = 0; i < items.length; i++) {
      const entry = items[i].webkitGetAsEntry();
      if (!entry) continue;

      // Only set rootFolderName if this entry is a directory
      if (entry.isDirectory && rootFolderName === null) {
        rootFolderName = entry.name;
      }

      // Walk every file/folder regardless
      traverseFileTree(entry);
    }
  } else {
    // Pure file-drop (no items API), clear out any folder name
    rootFolderName = null;
    uploadFiles(e.dataTransfer.files);
  }
});

  fileInput.addEventListener("change", () => {
    uploadFiles(fileInput.files);
  });
}

$("#loading-area")
  .hide() // Hide it initially
  .ajaxStart(function () {
    $(this).show();
  });
// .ajaxStop(function() {
//     $(this).hide();
// })

// Kick off your batch
function uploadFiles(fileList) {
  pendingUploads   = fileList.length;
  completedUploads = 0;
  uploadedDocs.length = 0;
  console.log("Uploading files");

  for (let i = 0; i < fileList.length; i++) {
    processFile(fileList[i]);
  }
}

// In your AJAX success:
success: result => {
  completedUploads++;
  if (result.uuid) {
    uploadedDocs.push({ name: filename, uuid: result.uuid });
  }
  // once _all_ files have reported back:
  if (completedUploads === pendingUploads) {
    finalizeUploads();
  }
}

function finalizeUploads() {
  // Example: append each as a new table row
  uploadedDocs.forEach(doc => {
    const newRow = $("<tr>");
    const newCell = $("<td>");
    const newLink = $("<a>")
      .attr("href", `/home?docid=${doc.uuid}`)
      .text(doc.name);
    newCell.append(newLink);
    newRow.append(newCell);
    $("#doc-body").append(newRow);
  });

  // OR, if you’d rather send them all to a “batch view”:
  // window.location.href = `/home?uploaded=${uploadedDocs.map(d => d.uuid).join(",")}`;
}

// Recursively walk directories
function traverseFileTree(entry, path = "") {
  if (entry.isFile) {
    entry.file(file => {
      // you can reconstruct full relative path if needed:
      file.relativePath = path + file.name;
      processFile(file);
    });
  } else if (entry.isDirectory) {
    const dirReader = entry.createReader();
    dirReader.readEntries(entries => {
      entries.forEach(en => traverseFileTree(en, path + entry.name + "/"));
    });
  }
}

function processFile(file) {
  const validTypes = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  ];
  if (!validTypes.includes(file.type)) {
    console.warn(`${file.name} is not a supported document type.`);
    return;
  }

  const reader = new FileReader();
  reader.onload = () => {
    const arrayBuffer = reader.result;
    const base64String = arrayBufferToBase64(arrayBuffer);
    const filename = file.relativePath || file.name;
    const extension = filename.split(".").pop();

    const payload = {
        contentType: file.type,
        contentAsBase64String: base64String,
        fileName: filename,
        extension,
        space: document.querySelector("#current-space-id").innerText,
        folder: document.querySelector("#current-folder-id").innerText,
        rootFolderName  // <-- new
        };

    // Show loader for each file if you like
    $("#loading-area").show();
    $("#drag-area").hide();

    $.ajax({
      type: "POST",
      url: "/files/upload",
      data: JSON.stringify(payload),
      processData: false,
      contentType: "application/json",
      dataType: "json",
      success: result => {
        completedUploads++;
        if (result.uuid) {
            uploadedDocs.push({ name: filename, uuid: result.uuid });
        }

        console.log(`Uploaded ${completedUploads} of ${pendingUploads}`);
        // All done?
        if (completedUploads === pendingUploads) {
            if (pendingUploads === 1) {
            // Single-file: go straight to that doc
            window.location.href = `/home?docid=${result.uuid}`;
            } else {
            // Multi-file: reload the list
            window.location.href = '/home';
            }
        }
      },
      error: err => {
        console.error(`Error uploading ${filename}`, err);
      },
      complete: () => {
        $("#loading-area").hide();
        $("#drag-area").show();
      }
    });
  };
  reader.readAsArrayBuffer(file);
}

function arrayBufferToBase64(buffer) {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  bytes.forEach(b => binary += String.fromCharCode(b));
  return window.btoa(binary);
}