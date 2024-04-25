//toggle mode
const modeToggleBtn = document.getElementById('modeToggle');
const htmlElement = document.getElementById('htmlElement');

    // Check if data-theme attribute is already set, if not, set it based on user's preference
document.addEventListener('DOMContentLoaded', () => {
    if (!htmlElement.getAttribute('data-theme')) {
        const prefersDarkScheme = window.matchMedia("(prefers-color-scheme: dark)");
        if (prefersDarkScheme.matches) {
            htmlElement.setAttribute('data-theme', 'dark');
        } else {
            htmlElement.setAttribute('data-theme', 'light');
        }
    }
});
modeToggleBtn.addEventListener('click', () => {
    // Toggle 'dark' and 'light' themes on the <html> element
    if (htmlElement.getAttribute('data-theme') === 'dark') {
        htmlElement.setAttribute('data-theme', 'light');
    } else {
        htmlElement.setAttribute('data-theme', 'dark');
    }
});

// Function to handle instance select change event
function handleInstanceSelectChange() {
    // Event listener for change event of instanceSelect
    document.getElementById('instanceSelect').addEventListener('change', function() {
        var instanceId = this.value;
        if (instanceId) {
            statusIndicator.classList.remove('green', 'red');
            getData(instanceId);
        } else {
            statusIndicator.classList.remove('green', 'red');
        }
    });
}

// Function to reattach event listener after saving changes and reopening the page
function reattachInstanceSelectChange() {
    // Remove existing event listener
    document.getElementById('instanceSelect').removeEventListener('change', handleInstanceSelectChange);
    // Reattach event listener
    handleInstanceSelectChange();
}

// Call the function at page start
document.addEventListener('DOMContentLoaded', function() {
    handleInstanceSelectChange();
});


// Function to reload the instance selector content via AJAX
function reloadInstanceSelector() {
    fetch('/get_config', {
        method: 'POST',  // Sending a POST request
        headers: {
            'Content-Type': 'application/json'  // Assuming the server expects JSON data
        },
        // Optionally, include a request body if needed
        body: JSON.stringify({})  // You can pass data in the body if required
    })
    .then(response => response.json())
    .then(data => {
        // console.log('Received data from server:', data); // Debug statement
        // Clear existing options
        var instanceSelect = document.getElementById('instanceSelect');
        instanceSelect.innerHTML = '';

        // Add new options to instance selector
        data.config_data.instances.forEach(function(instance) {
            var optionElement = document.createElement('option');
            // console.log('optionElement:', optionElement); // Debug statement
            optionElement.value = instance.id;
            optionElement.textContent = instance.name;
            instanceSelect.appendChild(optionElement);
        });

        // Reinitialize event listener
        handleInstanceSelectChange();
        handleSuccess();
    })
    .catch(error => {
        console.error('Error fetching instance options:', error);
    });
}





//get the instance data
function getData() {
    var instanceId = document.getElementById('instanceSelect').value;

    // Display "Fetching..." placeholder text
    document.getElementById('configInput').value = 'Fetching...';
    document.getElementById('commandLineInput').value = 'Fetching...';

    // Set up a timeout promise
    const timeoutPromise = new Promise((resolve, reject) => {
        setTimeout(() => {
            reject(new Error('Timeout')); // Reject the promise after 10 seconds
        }, 10000); // 10 seconds timeout
    });

    // Race between the fetch request and the timeout promise
    Promise.race([
        timeoutPromise,
        fetch('/get_data', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: 'instance_id=' + instanceId
        })
        .then(response => response.json())
        //.then(response => response.text()) //TEXT variant
        .then(data => {
            // Assuming data is an object with two properties: config_data and commandline_data

            var configData = JSON.stringify(data.config_data, null, 2);
            //var configData = data.config_data; //TEXT variant
            var commandLineData = data.commandline_data ? data.commandline_data.replace(/["\n]/g, '') : ''; // Replace with empty string if data is undefined
            // document.getElementById('configInput').value = configData;
            document.getElementById('configInput').value = configData;
            document.getElementById('commandLineInput').value = commandLineData;

            //update statusIndicator
            var statusIndicator = document.getElementById('statusIndicator'); // element for the indicator
            var BotActive = data.bot_status
            updateStatusIndicator(statusIndicator, BotActive);


            //update available actions
            var updateButton = document.getElementById('updateButton'); // element for the indicator
            var update_available = data.update_available
            //do something with the button.

            // Check the value of the update_available variable
            if (update_available) {
                // If update is available, show the button
                updateButton.style.visibility = 'visible';
                updateButton.style.animation = 'blinking 1s infinite'; // Add blinking animation
            } else {
                // If update is not available, hide the button
                updateButton.style.visibility = 'hidden';
            }


            //reload the log
            handleSuccess();
        })

        .catch(error => {
            // Handle fetch errors
            console.error(error);
            document.getElementById('configInput').value = 'Failed to fetch data';
            document.getElementById('commandLineInput').value = 'Failed to fetch data';
            handleError(error)
        })
    ]);
}

function editInstances() {
    fetch('/get_config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded'
        },
        // Optionally, you can include a body if needed
        // body: 'key1=value1&key2=value2'
    })
    .then(response => response.json())
    .then(data => {
        // Assuming data is an object with two properties: config_data and commandline_data
        var configData = JSON.stringify(data.config_data, null, 2);
        document.getElementById('configInput').value = configData;

        handleSuccess(); //reload the log

    })
    .catch(error => {
        // Handle fetch errors
        console.error(error);
        // Handle error here
    });
}

//update the bot status indicator
function updateStatusIndicator(statusIndicator, BotActive) {
    // Remove any existing classes
    statusIndicator.classList.remove('green', 'red');

    // Update the status indicator based on the value of bot_active
    if (BotActive) {
        statusIndicator.classList.add('green'); // Add green class to show active status
    } else {
        statusIndicator.classList.add('red'); // Add red class to show inactive status
    }
}

function confirmSaveJSON() {
        // Display a confirmation dialog
        if (window.confirm('Are you sure you want to save the JSON?')) {
            // If the user clicks OK, call the restartApplication function
            saveJSON();
        } else {
            // If the user clicks Cancel, do nothing
            console.log('canceled');
        }
    }

function saveJSON() {
    var instanceId = document.getElementById('instanceSelect').value;
    var json = document.getElementById('configInput').value;

    fetch('/save_json', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded'
        },
        body: 'instance_id=' + instanceId + '&json=' + encodeURIComponent(json)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // alert('JSON saved successfully!');

            //setTimeout(reattachInstanceSelectChange, 3000)
            reloadInstanceSelector();
            handleSuccess();

            //handleInstanceSelectChange()
            // reattachInstanceSelectChange

        } else {
            alert('Failed to save JSON: ' + data.error);
            handleError(error)
        }
    })
    .catch(error => {
        alert('Failed to parse JSON: ' + error.message);
        handleError(error)
    });
}


function confirmRestartApplication() {
        // Display a confirmation dialog
        if (window.confirm('Are you sure you want to (re)start?')) {
            // If the user clicks OK, call the restartApplication function
            restartApplication();
        } else {
            // If the user clicks Cancel, do nothing
            console.log('canceled');
        }
    }

function restartApplication() {
    var instanceId = document.getElementById('instanceSelect').value;
    var commandLineData = document.getElementById('commandLineInput').value;
    fetch('/restart_application', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded'
        },
        body: 'instance_id=' + instanceId + '&commandLineData=' + encodeURIComponent(commandLineData)
    })
//TODO: if commandlinedata is different than instance[ds start command]. notify and save?
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            //alert('StartCommand saved en DS (re)started successfully');
            getData(instanceId)
            handleSuccess()

        } else {
            alert('Failed to restart application: ' + data.error);
            handleError(data.error)
        }
    });
}

function confirmStopApplication() {
        // Display a confirmation dialog
        if (window.confirm('Are you sure you want to stop?')) {
            // If the user clicks OK, call the restartApplication function
            StopApplication();
        } else {
            // If the user clicks Cancel, do nothing
            console.log('canceled');
        }
    }

function StopApplication() {
    var instanceId = document.getElementById('instanceSelect').value;
    var commandLineData = document.getElementById('commandLineInput').value;
    fetch('/stop_application', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded'
        },
        body: 'instance_id=' + instanceId
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            //alert('StopCommand successfully');
            handleSuccess()
            getData(instanceId)
        } else {
            alert('Failed to stop application: ' + data.error);
            handleError(data.error)
        }
    });
}


function confirmUpdateApplication() {
        // Display a confirmation dialog
        if (window.confirm('Are you sure you want to update?')) {
            // If the user clicks OK, call the updateApplication function
            updateApplication();
        } else {
            // If the user clicks Cancel, do nothing
            console.log('canceled');
        }
    }

function updateApplication() {
    var instanceId = document.getElementById('instanceSelect').value;
    fetch('/update_application', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded'
        },
        body: 'instance_id=' + instanceId
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            //alert('Git pull successful!');
            handleSuccess();
        } else {
            alert('ERROR: ' + data.error);
            handleError(data.error)
        }
    });
}


// Function to fetch log file contents from the server and update the textbox
function updateLog() {
    fetch('/get_log')
        .then(response => response.text())
        .then(data => {

            //for reverse order in textarea:

            // Split the data into lines, reverse the order, and join them back
            //var reversedData = data.split('\n').reverse().join('\n');
            //document.getElementById('logTextarea').value = reversedData;

            // Update the contents of the log textbox
            document.getElementById('logTextarea').value = data;

            // Scroll to the bottom of the log textbox
            logTextarea.scrollTop = logTextarea.scrollHeight;

        })
        .catch(error => {
            console.error('Error fetching log:', error);
        });
}

// Call the updateLog function when the page loads
//window.onload = updateLog;

// Function to handle successful operation
function handleSuccess() {
    // Update the log textbox after a successful operation
    updateLog();
}

// Function to handle error
function handleError(error) {
    // Update the log textbox after an error
    console.error('Error:', error);
    // Update the log textbox
    updateLog();
}

// Call the updateLog function when the page loads
window.onload = updateLog;
// also updateLog() every minute
setInterval(updateLog, 60000); // 60000 milliseconds = 1 minute

