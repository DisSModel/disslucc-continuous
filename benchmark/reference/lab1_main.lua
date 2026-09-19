--------------------------------------------------------------
-- This file contains a LUCCME APPLICATION MODEL definition --
--               Compatible with LuccME 3.1                 --
--        Generated with LuccMe Model Configurator          --
--               25/09/2017 at 11:57:26                     --
--------------------------------------------------------------

--------------------------------------------------------------
-- Creating Terraview Project                               --
--------------------------------------------------------------

import("gis")

local projFile = File("t3mp.tview")
if(projFile:exists()) then
	projFile:delete()
end

proj = Project {
	file = "t3mp.tview",
	clean = true
}

l1 = Layer{
	project = proj,
	name = "csAC",
	file = "../data/cs_ac/csAC.shp"
}

--------------------------------------------------------------
-- LuccME Model                                             --
--------------------------------------------------------------

import("luccme")

dofile("lab1_submodel.lua")


--------------------------------------------------------------
-- LuccME APPLICATION MODEL DEFINITION                      --
--------------------------------------------------------------
Lab1 = LuccMEModel
{
	name = "Lab1",

	-----------------------------------------------------
	-- Temporal dimension definition                   --
	-----------------------------------------------------
	startTime = 2008,
	endTime = 2014,

	-----------------------------------------------------
	-- Spatial dimension definition                    --
	-----------------------------------------------------
	cs = CellularSpace
	{
		project = proj,
		layer = "csAC",
		xy      = { "col", "row" },
		cellArea = 25,
	},


	-----------------------------------------------------
	-- Land use variables definition                   --
	-----------------------------------------------------
	landUseTypes =
	{
		"f", "d", "outros"
	},

	landUseNoData = "outros",

	-----------------------------------------------------
	-- Behaviour dimension definition:                 --
	-- DEMAND, POTENTIAL AND ALLOCATION COMPONENTS     --
	-----------------------------------------------------
	demand = D1,
	potential = P1,
	allocation = A1,

	save  =
	{
		outputTheme = "Lab1_",
		mode = "multiple",
		saveYears = {2014},
		saveAttrs = 
		{
			"d_out",
		},

	},

	isCoupled = false
}  -- END LuccME application model definition

-----------------------------------------------------
-- ENVIROMMENT DEFINITION                          --
-----------------------------------------------------
timer = Timer
{
	Event
	{
		start = Lab1.startTime,
		action = function(event)
					Lab1:run(event)
					
				  end
	},

	Event
	{
		start = Lab1.startTime,
		action = function(event)
					-- Após computePotential, adicione:
if (event:getTime() == 2009) then
    local count = 0
    local sum_pot = 0
    for k, cell in pairs(Lab1.cs.cells) do
        if count < 5 then
            print(string.format("Cell %d: f_pot=%.4f, d_pot=%.4f", k, cell['f_pot'], cell['d_pot']))
            count = count + 1
        end
        sum_pot = sum_pot + cell['d_pot']
    end
    print(string.format("Mean d_pot: %.4f", sum_pot / #Lab1.cs.cells))
end
					
				  end
	},

	Event{
		start = Lab1.startTime,
			action =  Map{
				target = Lab1.cs,
				select = "f",
				min = 0.0,
				max = 1.0,
				grouping = 'equalsteps',
				slices = 5,
				color = "Greens"
			}}
}

env_Lab1 = Environment{}
env_Lab1:add(timer)

-----------------------------------------------------
-- ENVIROMMENT EXECUTION                           --
-----------------------------------------------------
if Lab1.isCoupled == false then
	tsave = databaseSave(Lab1)
	env_Lab1:add(tsave)
	env_Lab1:run(Lab1.endTime)
	--saveSingleTheme(Lab1, true)
	projFile = File("t3mp.tview")
	if(projFile:exists()) then
		projFile:delete()
	end
end
