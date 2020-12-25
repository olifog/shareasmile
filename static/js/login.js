
function GetURLParameter(sParam) {
    var sPageURL = decodeURI(window.location.search.substring(1));
    var sURLVariables = sPageURL.split('&');
    for (var i = 0; i < sURLVariables.length; i++) {
        var sParameterName = sURLVariables[i].split('=');
        if (sParameterName[0] === sParam) {
            return sParameterName[1];
        }
    }
}

const name = GetURLParameter("name").replace(/\+/g,' ');


function callREST(e) {
    e.preventDefault();
    var params = "username=" + name + "&password=" + document.getElementById("password").value;
    var xhttp = new XMLHttpRequest();
    xhttp.onreadystatechange = function () {
        if (this.readyState === 4 && this.status === 200) {
            window.location.href = '../../redeem/' + GetURLParameter("redeem");
        } else if (this.readyState === 4 && this.status === 401) {
            document.getElementById("response").innerHTML = "Sorry, wrong password.";
        }
    };
    xhttp.open("POST", "/auth", true);
    xhttp.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    xhttp.send(params);
}

document.getElementById("form").addEventListener("submit", callREST, false)
document.getElementById("start").innerHTML = "Hello <b>" + name + "</b>!<br>Please input your password below:";
