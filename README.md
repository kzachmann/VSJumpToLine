# VSJumpToLine

I also like using Visual Studio as an editor for projects that do not use the Microsoft compiler because I do not want to miss the powerful features and plugins. Besides, it's a habit thing.
To start the compilation, I integrate the makefiles or build scripts as external tools in Visual Studio. The output of these external tools ends in the output window of Visual Studio.
If the external compiler now displays error messages or warnings, I would like to jump directly to the line of code where the error occurred by clicking on it.
Unfortunately, this does not work directly for GCC, Doxygen, and other tools because Visual Studio does not know the specific format.
**_VSJumpToLine_** __converts the output of these tools into a Visual Studio readable format. This can then be used in the output window of Visual Studio to jump to the corresponding line in the editor.__
Another feature is that _errors_, _warnings_ and _notes_ are grouped and all messages in between are filtered out. So you can quickly concentrate on the essentials.

**The focus is on GCC support, but other tools may work as well.**

### Usage example
The example uses a deliberately flawed "Hello World!" _C_ Program.
It is built with GCC on Windows with the help of _mingw-w64_. More specifically with _Win-builds_ (https://mingw-w64.org/doku.php/download/win-builds).

#### Build with GCC:
`gcc.exe -Wall -Wextra hello_world.c 2>&1 | mtee/+ tool_output.txt`

The tool [mtee](https://github.com/ritchielawrence/mtee) which is used in the line above sends any data it receives to stdout _and_ to a file, in our special case in the file _tool_output.txt_.
This file will later serve as an input file for _VSJumpToLine_.

##### Output (stdout)
Also content of  _tool_output.txt_.
```
hello_world.c: In function 'main':
hello_world.c:5:13: note: #pragma message: some message1
     #pragma message "some message1"
             ^
hello_world.c:8:10: error: redeclaration of 'unused_var2' with no linkage
     char unused_var2;
          ^
hello_world.c:7:10: note: previous declaration of 'unused_var2' was here
     char unused_var2;
          ^
hello_world.c:9:13: note: #pragma message: some message2
     #pragma message "some message2"
             ^
hello_world.c:10:5: warning: format '%u' expects a matching 'unsigned int' argument [-Wformat=]
     printf("Hello World! %u\n");
     ^
hello_world.c:8:10: warning: unused variable 'unused_var2' [-Wunused-variable]
     char unused_var2;
          ^
hello_world.c:6:10: warning: unused variable 'unused_var1' [-Wunused-variable]
     char unused_var1;
          ^
```
#### Run VSJumpToLine:

`VSJumpToLine.py -f tool_output.txt -m3`

##### Output (stdout)
The messages are now in Visual Studio format and nicely grouped.

```
jtol: ----------------------------------------------------------------------------------------------------
jtol: --------------------------------------- VSJumpToLine v1.0.0 ----------------------------------------
jtol: ----------------------------------------------------------------------------------------------------
jtol: options:
jtol: --filename: <tool_output.txt>
jtol: --filename: size: <857B>, modified: <2019-01-16T20:14:26>
jtol: --directory: <>
jtol: --prefix: <>, --multi: <3>, --suppress: <0>, --compact: <0>
jtol: ----------------------------------------------------------------------------------------------------
jtol: +++++++++++++++++++++++++++++++++++++++++++++ notes: 3 +++++++++++++++++++++++++++++++++++++++++++++
hello_world.c: In function 'main':
hello_world.c(5,13): note: #pragma message: some message1
     #pragma message "some message1"
             ^

hello_world.c(7,10): note: previous declaration of 'unused_var2' was here
     char unused_var2;
          ^

hello_world.c(9,13): note: #pragma message: some message2
     #pragma message "some message2"
             ^
jtol: ******************************************* warnings: 3 ********************************************
hello_world.c(10,5): warning: format '%u' expects a matching 'unsigned int' argument [-Wformat=]
     printf("Hello World! %u\n");
     ^

hello_world.c(8,10): warning: unused variable 'unused_var2' [-Wunused-variable]
     char unused_var2;
          ^

hello_world.c(6,10): warning: unused variable 'unused_var1' [-Wunused-variable]
     char unused_var1;
          ^
jtol: ############################################ errors: 1 #############################################
hello_world.c(8,10): error: redeclaration of 'unused_var2' with no linkage
     char unused_var2;
          ^
jtol: ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
jtol: finished (totals): time: 0.02s, errors: 1/0, warnings: 3/0, notes: 3/0, lines: 22
jtol: ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
```

#### Options:
More features are available, such as duplicate message hiding and directory lookup for files with no relative or absolute path.
But this is not explained in detail here. Just use the following command to display the options and help.

`VSJumpToLine.py -h`

### Suggestion
* If you want to color the whole thing I recommend you to have a look at [VSColorOutput](https://github.com/mike-ward/VSColorOutput) or at the [Microsoft marketplace](https://marketplace.visualstudio.com/items?itemName=MikeWard-AnnArbor.VSColorOutput).
* For people who can not use Python for some reason there is also a Windows _VSJumpToLine.exe_ in the repo (created with [pyinstaller](http://www.pyinstaller.org/)).
