//selecting all required elements
var file;
let dropArea = document.querySelector(".drag-area");
if (dropArea) {
  let dragText = dropArea.querySelector("header"),
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
    console.log("leave");
    dropArea.classList.remove("active");
    dragText.textContent = "Drag & Drop to Upload File";
  });

  //If user drop File on DropArea
  dropArea.addEventListener("drop", (event) => {
    event.preventDefault(); //preventing from default behaviour
    //getting user select file and [0] this means if user select multiple files then we'll select only the first one
    dragText.textContent = "Drag & Drop to Upload File";
    console.log("Looking for ifle");
    file = event.dataTransfer.files[0];
    console.log(file);
    showFile(); //calling function
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

function showFile() {
  console.log("beginning upload");
  let fileType = file.type; //getting selected file type
  let validExtensions = ["application/pdf"]; //adding some valid image extensions in array
  if (validExtensions.includes(fileType)) {
    //if user selected file is an image file
    let fileReader = new FileReader(); //creating new FileReader object
    fileReader.onload = () => {
      let fileURL = fileReader.result; //passing user file source in fileURL variable
      // UNCOMMENT THIS BELOW LINE. I GOT AN ERROR WHILE UPLOADING THIS POST SO I COMMENTED IT
      //let imgTag = `<img id="image" src="/static/images/images.jpeg" alt="image">`; //creating an img tag and passing user selected file source inside src attribute
      //dropArea.innerHTML = imgTag;
      $("#loading-area").show();
      $("#drag-area").hide();
      var filetype = file.type;
      var filename = file.name;
      var base64String = getB64Str(fileURL);

      var model = {
        contentType: filetype,
        contentAsBase64String: base64String,
        fileName: filename,
        space: $("#current-space-id")[0].innerHTML,
        folder: $("#current-folder-id")[0].innerHTML,
      };

      console.log(model);

      $.ajax({
        type: "POST",
        url: "/upload",
        data: JSON.stringify(model),
        processData: false,
        contentType: "application/json",
        dataType: "json",
        success: function (result) {
          console.log("upload succeeded");
          console.log(result);
          $("#loading-area").hide();
          $("#drag-area").show();
          let newRow = $("<tr>");
          let newCell = $("<td>");
          let newLink = $("<a>")
            .attr("href", "/home?docid=" + result.uuid)
            .text(filename);
          let href = "/home?folder_id=" + result.folder_id;
          window.location.href = href;
          return;

          newCell.append(newLink);
          newRow.append(newCell);

          $("#doc-body").append(newRow);
        },
      }); //adding that created img tag inside dropArea container
    };
    fileReader.readAsArrayBuffer(file);
  } else {
    alert("This is not a PDF!");
    dropArea.classList.remove("active");
    dragText.textContent = "Drag & Drop to Upload File";
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

$(document).ready(function () {
  const $popupMenu = $("#file-popup-menu");
  let currentItemId = null;
  let currentItemType = null;
  let isPopupJustOpened = false;

  $("#file-list tr").on("contextmenu", function (e) {
    e.preventDefault();
    showPopupMenu(e, $(this), $(this));
  });

  $(".ellipsis-btn").on("click", function (e) {
    e.preventDefault();
    e.stopPropagation();
    showPopupMenu(e, $(this).parent(), $(this));
  });

  function showPopupMenu(e, $target, $displaytarget) {
    const rect =
      e.type === "contextmenu"
        ? {
            left: e.clientX,
            top: e.clientY,
            bottom: e.clientY,
          }
        : $displaytarget[0].getBoundingClientRect();

    const popupHeight = $popupMenu.outerHeight();
    const windowHeight = $(window).height();

    let top, left;

    top = rect.top - 45;

    left = rect.left - 25;

    // Ensure the popup doesn't go off-screen horizontally
    const rightEdge = left + $popupMenu.outerWidth();
    if (rightEdge > $(window).width()) {
      left = $(window).width() - $popupMenu.outerWidth() - 5;
    }

    $popupMenu
      .css({
        top: `${top}px`,
        left: `${left}px`,
        display: "block",
        transform: "scale(1)",
        opacity: 0,
      })
      .animate(
        {
          transform: "scale(1)",
          opacity: 1,
        },
        200,
      );

    currentItemId = $target.find(".ellipsis-btn").data("folderId")
      ? $target.find(".ellipsis-btn").data("folderId")
      : $target.find(".ellipsis-btn").data("docId");
    currentItemType = $target.find(".ellipsis-btn").data("folderId")
      ? "folder"
      : "document";
    console.log(`Current item ID: ${currentItemId}, type: ${currentItemType}`);
    // Set the flag to true
    isPopupJustOpened = true;

    console.log(currentItemId);
    console.log(currentItemType);

    // Reset the flag after a short delay
    setTimeout(() => {
      isPopupJustOpened = false;
    }, 50);
  }

  $("#rename-option").on("click", function () {
    // Implement rename functionality
    console.log(`Rename ${currentItemType} with ID: ${currentItemId}`);
    let renameModal = $("#renameModal");

    $("#renameBtn")
      .off("click")
      .on("click", function () {
        let newName = $("#newName")[0].value;
        console.log(
          `Renaming ${currentItemType} with ID: ${currentItemId} to ${newName}`,
        );
        if (currentItemType === "folder") {
          console.log("renaming folder");
          renameFolder(currentItemId, newName);
        } else {
          console.log("renaming document");
          renameDocument(currentItemId, newName);
        }
      });

    $("#renameModal").show();
    hidePopupMenu();
  });

  function renameDocument(uuid, newName) {
    $.ajax({
      type: "POST",
      url: "/rename_document",
      data: JSON.stringify({ uuid: uuid, newName: newName }),
      processData: false,
      contentType: "application/json",
      dataType: "json",
      success: function (result) {
        console.log("rename succeeded");
        console.log(result);
        location.reload();
      },
    });
  }

  function renameFolder(uuid, newName) {
    $.ajax({
      type: "POST",
      url: "/rename_folder",
      data: JSON.stringify({ uuid: uuid, newName: newName }),
      processData: false,
      contentType: "application/json",
      dataType: "json",
      success: function (result) {
        console.log("rename succeeded");
        console.log(result);
        location.reload();
      },
    });
  }

  $("#delete-option").on("click", function () {
    // Implement delete functionality
    if (currentItemType === "folder") {
      if (confirm("Are you sure you want to delete this folder?")) {
        window.location.href = `/files/delete_folder?folder_id=${currentItemId}`;
      }
    } else {
      var folderId = null;
      var href = window.location.href;
      var folderIdIndex = href.indexOf("folder_id=");
      if (folderIdIndex !== -1) {
        folderId = href.substring(folderIdIndex + 10);
      }

      if (folderId) {
        window.location.href = `/delete_document?docid=${currentItemId}&folder_id=${folderId}`;
      } else {
        window.location.href = `/delete_document?docid=${currentItemId}`;
      }
    }
    hidePopupMenu();
  });

  $("#toggle-default-doc-option").on("click", function () {
    if (currentItemType !== "folder") {
      var folderId = null;
      var href = window.location.href;
      var folderIdIndex = href.indexOf("folder_id=");
      if (folderIdIndex !== -1) {
        folderId = href.substring(folderIdIndex + 10);
      }
      var redirectUrl = window.location.href.split("?")[1];
      console.log("redirectUrl: ", redirectUrl);
      window.location.href = `/files/toggle_default_doc?doc_id=${currentItemId}&redirect_url=${redirectUrl}`;
    } else {
      alert("You can only toggle document as default and not a folder.");
    }
    hidePopupMenu();
  });

  function hidePopupMenu() {
    $popupMenu.animate(
      {
        transform: "scale(0.8)",
        opacity: 0,
      },
      200,
      function () {
        $(this).hide();
      },
    );
  }

  // Close the popup menu when clicking outside
  $(document).on("click", function (e) {
    if (
      !isPopupJustOpened &&
      !$popupMenu.is(e.target) &&
      $popupMenu.has(e.target).length === 0 &&
      !$(e.target).hasClass("ellipsis-btn")
    ) {
      hidePopupMenu();
    }
  });

  const $fileList = $("#file-list");
  const $loadingIndicator = $("#loading");
  let $draggedItem = null;

  $fileList.on({
    dragstart: function (e) {
      const $target = $(e.target);
      if ($target.hasClass("file")) {
        $draggedItem = $target;
        setTimeout(() => $target.addClass("dragging"), 0);
      } else {
        e.preventDefault(); // Prevent dragging folders
      }
    },
    dragend: function (e) {
      $(e.target).removeClass("dragging");
    },
    dragover: function (e) {
      e.preventDefault();
      const $targetItem = $(e.target).closest(".file-item");
      if ($targetItem.length && $targetItem.hasClass("folder")) {
        $targetItem.addClass("drag-over");
      }
    },
    dragleave: function (e) {
      $(e.target).closest(".file-item").removeClass("drag-over");
    },
    drop: function (e) {
      e.preventDefault();
      const $targetItem = $(e.target).closest(".file-item");
      if (
        $targetItem.length &&
        $targetItem.hasClass("folder") &&
        !$draggedItem.is($targetItem)
      ) {
        $targetItem.removeClass("drag-over");
        $loadingIndicator.show();
        // Simulating an Ajax call
        setTimeout(() => {
          $loadingIndicator.hide();
          alert(
            `File "${$draggedItem.text()}" moved to "${$targetItem.text()}" folder`,
          );
          // In a real application, you would make an actual Ajax call here
          // and update the UI based on the server response
          $draggedItem.remove();
        }, 1000); // Simulating a 1-second delay
      }
    },
  });

  // Prevent opening the default drag-and-drop window in the browser
  $(document).on({
    dragover: function (e) {
      e.preventDefault();
    },
    drop: function (e) {
      e.preventDefault();
    },
  });
});
