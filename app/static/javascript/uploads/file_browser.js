

$(document).ready(function () {
  const $popupMenu = $("#file-popup-menu");
  let currentItemId = null;
  let currentItemType = null;
  let isPopupJustOpened = false;

  $("#file-list").on("contextmenu", "tr", function (e) {
    // If the target is inside an anchor or button, suppress their default behavior
    if ($(e.target).closest("a, button").length) {
      e.preventDefault();
      e.stopImmediatePropagation();
    }
    e.preventDefault();
    e.stopPropagation();
    showPopupMenu(e, $(this), $(this));
  });

    $("#file-list")
    .on("contextmenu", "a, button", function (e) {
      e.preventDefault();
      e.stopImmediatePropagation();
      return false;
    })
    .on("mousedown", "a, button", function (e) {
      // Right mouse button = 2 (or e.which === 3 in jQuery)
      if (e.button === 2 || e.which === 3) {
        e.preventDefault();
        e.stopImmediatePropagation();
        return false;
      }
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
    function finishRename() {
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
  }

     $("#newName").on("keyup", function (event) {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault(); // Prevent the default behavior of adding a newline
            finishRename();
        }
    });

    $("#renameBtn")
      .off("click")
      .on("click", function () {

        finishRename();
        
      });

    $("#renameModal").show();
    $("#newName")[0].value = "";
    $("#newName")[0].focus();

    hidePopupMenu();
  });

  

  function renameDocument(uuid, newName) {
    $.ajax({
      type: "POST",
      url: "/files/rename_document",
      data: JSON.stringify({ uuid: uuid, newName: newName }),
      processData: false,
      contentType: "application/json",
      dataType: "json",
      success: function (result) {
        console.log("rename succeeded");
        console.log(result);
        if (result.error) {
          
          return; // Exit the function
        }


        location.reload();
      },
      error: function(xhr, status, thrownError) {
      // check for a 400 response
      if (xhr.status === 400) {
        // jQuery will auto-parse JSON into responseJSON if possible
        let err = (xhr.responseJSON && xhr.responseJSON.error)
                  || (function(){ try { return JSON.parse(xhr.responseText).error; } catch(e){} })()
                  || "Unknown error";
        alert(err);
      } else {
        // fallback for other HTTP errors
        alert("Request failed: " + xhr.status + " " + thrownError);
      }
      console.error("rename failed:", status, thrownError, xhr.responseText);
    }
    });
  }

  function renameFolder(uuid, newName) {
    $.ajax({
      type: "POST",
      url: "/files/rename_folder",
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
      let folderId = null;
      let href = window.location.href;
      let folderIdIndex = href.indexOf("folder_id=");
      if (folderIdIndex !== -1) {
        folderId = href.substring(folderIdIndex + 10);
      }

      if (folderId) {
        window.location.href = `/files/delete_document?docid=${currentItemId}&folder_id=${folderId}`;
      } else {
        window.location.href = `/files/delete_document?docid=${currentItemId}`;
      }
    }
    hidePopupMenu();
  });

  $("#download-option").on("click", function () {
    // Implement rename functionality
    window.location.href = `/files/download_document?docid=${currentItemId}`;
  });

  $("#toggle-default-doc-option").on("click", function () {
    if (currentItemType !== "folder") {
      let folderId = null;
      let href = window.location.href;
      let folderIdIndex = href.indexOf("folder_id=");
      if (folderIdIndex !== -1) {
        folderId = href.substring(folderIdIndex + 10);
      }
      let redirectUrl = window.location.href.split("?")[1];
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
  let $dragGhost = null;

  $fileList.on({
    dragstart: function (e) {
      const $target = $(e.target).closest(".file");
      if ($target.length) {
        $draggedItem = $target;
        setTimeout(() => $target.addClass("dragging"), 0);

        // Create ghost element to indicate dragging
        $dragGhost = $('<div class="drag-ghost">Moving file...</div>');
        $("body").append($dragGhost);
        $(document).on("mousemove", moveDragGhost);
      } else {
        e.preventDefault(); // Prevent dragging folders or other items
      }
    },
    dragend: function (e) {
      $(e.target).removeClass("dragging");
      if ($dragGhost) {
        $dragGhost.remove();
        $(document).off("mousemove", moveDragGhost);
      }
    },
    dragover: function (e) {
      e.preventDefault();
      const $targetItem = $(e.target).closest(".folder");
      if ($targetItem.length) {
        $targetItem.addClass("drag-over");
      } else {
        $(".folder").removeClass("drag-over"); // Remove the border from all folders if not dragging over any folder
      }
    },
    dragleave: function (e) {
      $(e.target).closest(".folder").removeClass("drag-over");
    },
    drop: function (e) {
      e.preventDefault();
      const $targetItem = $(e.target).closest(".folder");
      if ($targetItem.length && !$draggedItem.is($targetItem)) {
        $targetItem.removeClass("drag-over");
        $loadingIndicator.show();

        // Call the custom function when file is dropped on folder
        moveFileToFolder($draggedItem, $targetItem);

        setTimeout(() => {
          $loadingIndicator.hide();
          $draggedItem.remove();
        }, 1000); // Simulating a 1-second delay
      }

      // Remove dragging styles
      $draggedItem.removeClass("dragging");
      if ($dragGhost) {
        $dragGhost.remove();
        $(document).off("mousemove", moveDragGhost);
      }

      // Remove any leftover drag-over class from folders
      $(".folder").removeClass("drag-over");
    },
  });

  // Function to move the ghost element with the cursor
  function moveDragGhost(e) {
    $dragGhost.css({
      top: e.pageY + 10 + "px",
      left: e.pageX + 10 + "px",
    });
  }

  // Custom function to handle file move logic
  function moveFileToFolder($file, $folder) {
    // Implement any server-side call or other logic here
    console.log("Moving file");
    console.log($file);
    console.log($folder);
    // Get the data-doc-uuid of the file being moved
    const fileUUID = $file.find("input:first").data("doc-uuid");

    // Get the data-folder-id of the target folder
    const folderID = $folder.find("input:first").data("doc-uuid");

    console.log("File UUID:", fileUUID);
    console.log("Target Folder ID:", folderID);

    $.ajax({
      type: "POST",
      url: "/files/move_file",
      data: JSON.stringify({
        fileUUID: fileUUID,
        folderID: folderID,
      }),
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
